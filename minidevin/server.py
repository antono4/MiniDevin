"""MiniDevin web server v2: sessions, file explorer API, persistent config, stop support."""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import WORKSPACE, run_agent

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = BASE_DIR / ".minidevin"
SESSIONS_DIR = DATA_DIR / "sessions"
CONFIG_FILE = DATA_DIR / "config.json"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MiniDevin")

CONFIG = {
    "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
    "api_key": os.environ.get("LLM_API_KEY", ""),
    "base_url": os.environ.get("LLM_BASE_URL", ""),
}
if CONFIG_FILE.exists():
    try:
        saved = json.loads(CONFIG_FILE.read_text())
        CONFIG.update({k: v for k, v in saved.items() if v or k not in CONFIG})
    except Exception:
        pass


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
    DATA_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(CONFIG))
    return {"ok": True}


def _tree(root: Path, depth: int, limit: list) -> dict:
    node = {"name": root.name or ".", "type": "dir", "children": []}
    if depth <= 0 or limit[0] >= 300:
        return node
    try:
        entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name))
    except PermissionError:
        return node
    for e in entries:
        if limit[0] >= 300:
            break
        if e.name.startswith(".") or e.name == "__pycache__":
            continue
        limit[0] += 1
        if e.is_dir():
            node["children"].append(_tree(e, depth - 1, limit))
        else:
            node["children"].append({"name": e.name, "type": "file"})
    return node


@app.get("/api/files")
async def list_files():
    return _tree(WORKSPACE, 4, [0])


@app.get("/api/file")
async def read_file(path: str = Query(...)):
    p = (WORKSPACE / path).resolve()
    if not str(p).startswith(str(WORKSPACE) + os.sep) or not p.is_file():
        return JSONResponse({"error": "invalid path"}, status_code=400)
    try:
        return {"path": str(p.relative_to(WORKSPACE)), "content": p.read_text()[:100_000]}
    except UnicodeDecodeError:
        return JSONResponse({"error": "binary file"}, status_code=400)


@app.get("/api/sessions")
async def list_sessions():
    out = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
            out.append({"id": d["id"], "title": d.get("title", "Untitled"), "updated": d.get("updated", 0)})
        except Exception:
            continue
    return out[:50]


def _save_session(session: dict):
    session["updated"] = time.time()
    (SESSIONS_DIR / f"{session['id']}.json").write_text(json.dumps(session))


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    session = None
    history: list = []
    cancel = asyncio.Event()
    current_task: asyncio.Task | None = None

    async def emit(event: dict):
        if session is not None and event["type"] in ("thought", "message", "action", "observation", "error"):
            session["events"].append(event)
        await websocket.send_text(json.dumps(event))

    try:
        while True:
            data = json.loads(await websocket.receive_text())
            mtype = data.get("type")

            if mtype == "init":
                sid = data.get("session_id")
                f = SESSIONS_DIR / f"{sid}.json" if sid else None
                if f and f.exists():
                    session = json.loads(f.read_text())
                    history = session.get("history", [])
                else:
                    session = {"id": uuid.uuid4().hex[:12], "title": "Percakapan baru",
                               "updated": time.time(), "events": [], "history": []}
                await websocket.send_text(json.dumps({
                    "type": "session", "session_id": session["id"],
                    "title": session["title"], "events": session["events"],
                }))

            elif mtype == "new_session":
                session = {"id": uuid.uuid4().hex[:12], "title": "Percakapan baru",
                           "updated": time.time(), "events": [], "history": []}
                history = []
                await websocket.send_text(json.dumps({
                    "type": "session", "session_id": session["id"],
                    "title": session["title"], "events": [],
                }))

            elif mtype == "stop":
                cancel.set()
                if current_task and not current_task.done():
                    current_task.cancel()

            elif mtype == "chat":
                if session is None:
                    continue
                if not CONFIG["api_key"]:
                    await emit({"type": "error", "content": "LLM belum dikonfigurasi. Klik ⚙️ Settings dan masukkan API key Anda."})
                    continue
                if session["title"] == "Percakapan baru":
                    session["title"] = data["message"][:60]
                session["events"].append({"type": "user", "content": data["message"]})
                cancel = asyncio.Event()
                try:
                    current_task = asyncio.create_task(
                        run_agent(data["message"], history, CONFIG, emit, cancel)
                    )
                    await current_task
                    history.append({"role": "user", "content": data["message"]})
                    history.append({"role": "assistant", "content": "(task processed)"})
                    history[:] = history[-20:]
                    session["history"] = history
                except asyncio.CancelledError:
                    await emit({"type": "error", "content": "⏹️ Dihentikan oleh pengguna."})
                except Exception as e:
                    await emit({"type": "error", "content": f"Agent error: {e}"})
                finally:
                    _save_session(session)
    except WebSocketDisconnect:
        if current_task and not current_task.done():
            current_task.cancel()
        if session:
            _save_session(session)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(Exception)
async def on_error(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=500)
