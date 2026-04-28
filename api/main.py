from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from starlette.responses import JSONResponse

import config
import core.age_queries as age_queries

rebuild_flag: dict = {"running": False}

_api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def verify_api_key(key: str = Security(_api_key_header)) -> None:
    if not config.API_KEY:
        return
    if key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    age_queries.init(config.AGE_DSN, config.AGE_GRAPH)
    yield


app = FastAPI(title="Nexus", lifespan=lifespan)


@app.middleware("http")
async def rebuild_guard(request: Request, call_next):
    safe_paths = {"/health", "/docs", "/openapi.json", "/rebuild"}
    if rebuild_flag["running"] and request.url.path not in safe_paths:
        return JSONResponse({"detail": "Graph rebuild in progress"}, status_code=503)
    return await call_next(request)


from api.routes import graph as graph_routes
from api.routes import rebuild as rebuild_routes

app.include_router(graph_routes.router, prefix="/graph", dependencies=[Security(verify_api_key)])
app.include_router(rebuild_routes.router, prefix="/rebuild", dependencies=[Security(verify_api_key)])


@app.get("/health")
def health():
    return {"status": "ok"}
