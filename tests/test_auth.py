"""Service-to-service authentication (app/core/auth.py).

Tokens are signed with a key generated per run; the verifier's key fetch is
stubbed to publish its public half, so no Keycloak is involved.
"""

import base64
import hashlib
import hmac
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import Depends, FastAPI

from app.api.dependencies import get_db_pool
from app.core import auth
from app.core.config import settings
from app.main import app

ISSUER = "https://keycloak.example.org/realms/farmer"
AUDIENCE = "farmer-registry-dashboard-api"
ROLE = "charts:read"
KID = "test-key"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks(key=KEY, kid=KID) -> dict:
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {"keys": [{**public, "kid": kid, "use": "sig", "alg": "RS256"}]}


def token(key=KEY, kid=KID, algorithm="RS256", **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": [AUDIENCE, "account"],
        "azp": "farmer-registry-dashboard",
        "sub": "service-account-id",
        "iat": now,
        "exp": now + 300,
        "resource_access": {AUDIENCE: {"roles": [ROLE]}},
    }
    claims.update(overrides)
    return jwt.encode(
        {k: v for k, v in claims.items() if v is not None}, key, algorithm=algorithm, headers={"kid": kid}
    )


@pytest.fixture
def published(monkeypatch):
    """Turns authentication on; returns a setter for what the JWKS endpoint answers."""
    answer = {"value": jwks()}

    def fetch_data(_client):
        if isinstance(answer["value"], Exception):
            raise answer["value"]
        return answer["value"]

    monkeypatch.setattr(settings, "AUTH_ISSUER", ISSUER + "/")  # trailing slash is tolerated
    monkeypatch.setattr(settings, "AUTH_AUDIENCE", AUDIENCE)
    monkeypatch.setattr(settings, "AUTH_ROLE", ROLE)
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", fetch_data)
    auth.reset()
    yield lambda value: answer.update(value=value)
    auth.reset()


probe = FastAPI()


@probe.get("/probe")
async def whoami(caller: auth.Caller | None = Depends(auth.require_caller)):
    return {"client": caller.client_id if caller else None}


async def call(path="/probe", bearer: str | None = None, target=probe) -> httpx.Response:
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=target), base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_off_without_issuer(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ISSUER", "")
    auth.reset()
    try:
        res = await call()
        assert res.status_code == 200
        assert res.json() == {"client": None}
    finally:
        auth.reset()


async def test_accepts_a_valid_service_token(published):
    res = await call(bearer=token())
    assert res.status_code == 200
    assert res.json() == {"client": "farmer-registry-dashboard"}


async def test_audience_may_be_a_single_string(published):
    assert (await call(bearer=token(aud=AUDIENCE))).status_code == 200


async def test_missing_token_is_401_with_challenge(published):
    res = await call()
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == "Bearer"


async def test_non_bearer_scheme_is_401(published):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=probe), base_url="http://test") as client:
        res = await client.get("/probe", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert res.status_code == 401


@pytest.mark.parametrize(
    ("description", "bearer"),
    [
        ("expired", lambda: token(exp=int(time.time()) - 120)),
        ("other issuer", lambda: token(iss="https://evil.example.org/realms/farmer")),
        ("other audience", lambda: token(aud="account")),
        ("no audience", lambda: token(aud=None)),
        ("no expiry", lambda: token(exp=None)),
        ("signed by another key", lambda: token(key=OTHER_KEY)),
        ("unknown key id", lambda: token(kid="rotated-away")),
        ("not a JWT", lambda: "not-a-token"),
    ],
)
async def test_rejects_invalid_tokens(published, description, bearer):
    res = await call(bearer=bearer())
    assert res.status_code == 401, description
    assert res.headers["www-authenticate"].startswith('Bearer error="invalid_token"')


async def test_rejects_hmac_signed_with_the_public_key(published):
    # Algorithm confusion: an HS256 token whose "secret" is the realm's public
    # key. PyJWT refuses to sign that, so the token is assembled by hand.
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    public_pem = KEY.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 300,
        "resource_access": {AUDIENCE: {"roles": [ROLE]}},
    }
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = b64(json.dumps(claims).encode())
    signature = b64(hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    res = await call(bearer=f"{header}.{payload}.{signature}")
    assert res.status_code == 401


async def test_valid_token_without_the_role_is_403(published):
    res = await call(bearer=token(resource_access={AUDIENCE: {"roles": ["something-else"]}}))
    assert res.status_code == 403
    assert res.headers["www-authenticate"] == 'Bearer error="insufficient_scope"'


async def test_role_on_another_client_is_403(published):
    res = await call(bearer=token(resource_access={"farmer-registry-dashboard": {"roles": [ROLE]}}))
    assert res.status_code == 403


async def test_follows_key_rotation(published):
    published(jwks(OTHER_KEY, kid="new-key"))
    res = await call(bearer=token(key=OTHER_KEY, kid="new-key"))
    assert res.status_code == 200


async def test_unreachable_keys_are_503(published):
    published(jwt.PyJWKClientConnectionError("connection refused"))
    res = await call(bearer=token())
    assert res.status_code == 503


async def test_chart_routes_reject_before_touching_the_database(published):
    # The real app, with no database pool: a 401 proves authentication runs
    # before the router's database dependency.
    res = await call("/api/v1/charts/farmerKpis", target=app)
    assert res.status_code == 401


async def test_health_stays_open(published):
    # Probes carry no token; /health reveals nothing but liveness.
    class Conn:
        async def fetchval(self, _query):
            return 1

    class Acquire:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *_):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    app.dependency_overrides[get_db_pool] = lambda: Pool()
    try:
        assert (await call("/health", target=app)).status_code == 200
    finally:
        app.dependency_overrides.clear()


async def test_chart_with_valid_token(published, client):
    # Database-backed (skipped without TEST_DATABASE_URL): the full path.
    res = await client.get("/api/v1/charts/farmerKpis", headers={"Authorization": f"Bearer {token()}"})
    assert res.status_code == 200
    assert res.json()[0]["total_farmers"] == 3
