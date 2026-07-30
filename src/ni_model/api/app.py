import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes.population import router as population_router
from .routes.simulation import router as simulation_router

FRONTEND_DIST = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "frontend", "dist"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="NI Population Model API",
        description="Northern Ireland demographic simulation API",
        version="0.2.2",
        lifespan=lifespan,
    )
    app.include_router(population_router)
    app.include_router(simulation_router)
    if os.path.isdir(FRONTEND_DIST):
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
