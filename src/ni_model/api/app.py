import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..mcp.server import mcp
from .routes.population import router as population_router
from .routes.simulation import router as simulation_router

FRONTEND_DIST = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "frontend", "dist"
)
OWNER_COOKIE = "ni_model_owner"


mcp_http_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_http_app.lifespan(app):
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="NI Population Model API",
        description="Northern Ireland demographic simulation API",
        version=__version__,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def browser_run_identity(request: Request, call_next):
        owner_token = request.cookies.get(OWNER_COOKIE) or secrets.token_urlsafe(32)
        request.state.owner_token = owner_token
        response = await call_next(request)
        if OWNER_COOKIE not in request.cookies:
            response.set_cookie(
                OWNER_COOKIE,
                owner_token,
                max_age=365 * 24 * 60 * 60,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
            )
        return response

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        """Remain a cheap liveness probe while simulations run elsewhere."""
        return {"status": "ok"}

    app.include_router(population_router)
    app.include_router(simulation_router)
    app.mount("/mcp", mcp_http_app, name="mcp")
    if os.path.isdir(FRONTEND_DIST):
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
