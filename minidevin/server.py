"""MiniDevin web server: FastAPI + WebSocket chat + LLM settings."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import run_agent

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="MiniDevin")

CONFIG = {
    "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
    "api_key": os.environ.get("LLM_API_KEY", ""),
    "base_url": os.environ.get("LLM_BASE_URL", ""),
}


class Settings(BaseModel):
    model: str
    api_key: str
    base_url: str = ""


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def status():
    return {
        "configured": bool(CONFIG["api_key"]),
        "model": CONFIG["model"],
        "base_url": CONFIG["base_url"],
    }


@app.post("/api/settings")
async def save_settings(s: Settings):
    CONFIG.update(s.model_dump())
    return {"ok": True}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    history: list = []

    async def emit(event: dict):
        await websocket.send_text(json.dumps(event))

    try:
        while True:
            data = json.loads(await websocket.receive_text())
            if data.get("type") != "chat":
                continue
            if not CONFIG["api_key"]:
                await emit({"type": "error", "content": "LLM belum dikonfigurasi. Klik ⚙️ Settings dan masukkan API key Anda."})
                continue
            try:
                await run_agent(data["message"], history, CONFIG, emit)
                history.append({"role": "user", "content": data["message"]})
                history.append({"role": "assistant", "content": "(task processed)"})
                history[:] = history[-20:]
            except Exception as e:
                await emit({"type": "error", "content": f"Agent error: {e}"})
    except WebSocketDisconnect:
        pass


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(Exception)
async def on_error(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=500)
