from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncpg
from app.core.config import settings
from app.api.routes.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database pool
    app.state.pool = await asyncpg.create_pool(settings.DATABASE_URL)
    yield
    # Clean up the pool on shutdown
    await app.state.pool.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the main API router
app.include_router(api_router, prefix=settings.API_V1_STR)
