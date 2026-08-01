import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..mcp.server import mcp
from .routes.population import router as population_router
from .routes.simulation import router as simulation_router

FRONTEND_DIST = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "frontend", "dist"
)


mcp_http_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_http_app.lifespan(app):
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="NI Population Model API",
        description="Northern Ireland demographic simulation API",
        version="0.4.0",
        lifespan=lifespan,
    )

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
