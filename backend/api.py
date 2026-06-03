"""FastAPI app: one /api/query endpoint + the static Leaflet dashboard.

Run:  uvicorn backend.api:app --reload    (then open http://127.0.0.1:8000)
"""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import pipeline, config

app = FastAPI(title="Balloon Flight Planner")
FRONTEND = config.ROOT / "frontend"


class QueryReq(BaseModel):
    lat: float
    lon: float
    mode: str | None = None          # 'morning' | 'evening' (toggle)
    question: str | None = None      # pilot's flight question (optional)
    plan: bool = False               # run the LLM?
    name: str = "Takeoff"


@app.post("/api/query")
def api_query(req: QueryReq):
    return pipeline.query(req.lat, req.lon, req.question,
                          mode=req.mode, name=req.name, call_llm=req.plan)


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
