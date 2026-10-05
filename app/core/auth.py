"""Service-to-service authentication of chart requests.

The dashboards BFF calls this service with an access token it gets from the
registry's Keycloak with the client-credentials grant, as its own client. A
request is accepted when its `Authorization: Bearer` token:

  1. is signed by a key in the realm's JWKS, with an asymmetric algorithm;
  2. is not expired (AUTH_LEEWAY_SECONDS of clock skew allowed);
  3. was issued by AUTH_ISSUER;
  4. names AUTH_AUDIENCE, this service's Keycloak client, in `aud`;
  5. carries AUTH_ROLE among that client's roles (`resource_access`).

Keycloak puts a client in `aud` by itself when the token carries one of the
client's roles, so a caller needs no setup beyond that role on its service
account. No user is involved: the BFF caches chart rows across users and
refreshes them in the background, so the caller is always the BFF itself.

Answers follow RFC 6750: 401 with `WWW-Authenticate: Bearer` for a missing or
invalid token, 403 (`insufficient_scope`) for a valid token without the role,
and 503 when the signing keys cannot be fetched.

Off while AUTH_ISSUER is unset: every request is accepted, and the service must
then stay unreachable from outside its private network (see docs/security.md).
"""

import logging
from dataclasses import dataclass
from functools import cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

log = logging.getLogger(__name__)

# Asymmetric only. With an HMAC algorithm allowed, a token "signed" with the
# public key would verify (algorithm confusion).
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]

# How long fetched signing keys are trusted. An unknown key id (Keycloak
# rotated its keys) triggers a refetch regardless.
JWKS_CACHE_SECONDS = 300


@dataclass(frozen=True)
class Caller:
    """The authenticated client: Keycloak's `azp` (client id) and `sub`."""

    client_id: str
    subject: str


def _unauthorized(description: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=description,
        headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{description}"'},
    )


class TokenVerifier:
    def __init__(self, issuer: str, audience: str, role: str, jwks_url: str, leeway: int) -> None:
        self.issuer = issuer
        self.audience = audience
        self.role = role
        self.leeway = leeway
        self._jwks = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=JWKS_CACHE_SECONDS, timeout=5)

    def _decode(self, token: str) -> dict[str, Any]:
        # Blocking (the key fetch is plain urllib): run in a worker thread.
        key = self._jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=ALGORITHMS,
            audience=self.audience,
            issuer=self.issuer,
            leeway=self.leeway,
            options={"require": ["exp", "iss", "aud"]},
        )

    async def verify(self, token: str) -> Caller:
        try:
            claims = await run_in_threadpool(self._decode, token)
        except jwt.PyJWKClientConnectionError as error:
            log.error("cannot fetch the signing keys: %s", error)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Token verification is unavailable") from error
        except jwt.PyJWKClientError as error:
            # Typically a key id the realm does not publish.
            raise _unauthorized("Unknown signing key") from error
        except jwt.ExpiredSignatureError as error:
            raise _unauthorized("Token expired") from error
        except jwt.InvalidTokenError as error:
            raise _unauthorized("Invalid token") from error

        roles = ((claims.get("resource_access") or {}).get(self.audience) or {}).get("roles") or []
        caller = Caller(client_id=str(claims.get("azp") or ""), subject=str(claims.get("sub") or ""))
        if self.role not in roles:
            log.warning("client %r lacks role %r on %r", caller.client_id, self.role, self.audience)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {self.role} on {self.audience} required",
                headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
            )
        return caller


@cache
def get_verifier() -> TokenVerifier | None:
    """The verifier for the configured issuer; None while authentication is off."""
    issuer = (settings.AUTH_ISSUER or "").strip().rstrip("/")
    if not issuer:
        return None
    jwks_url = (settings.AUTH_JWKS_URL or "").strip() or f"{issuer}/protocol/openid-connect/certs"
    return TokenVerifier(issuer, settings.AUTH_AUDIENCE, settings.AUTH_ROLE, jwks_url, settings.AUTH_LEEWAY_SECONDS)


def reset() -> None:
    """Rebuild the verifier from the settings on next use (tests)."""
    get_verifier.cache_clear()


async def require_caller(request: Request) -> Caller | None:
    """FastAPI dependency: the authenticated caller, or None while authentication is off."""
    verifier = get_verifier()
    if verifier is None:
        return None
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await verifier.verify(token.strip())
