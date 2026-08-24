"""MiniDevin web server v3: sessions, files, upload, git log, plan mode."""

import asyncio
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import WORKSPACE, WORKSPACES_ROOT, git_snapshot, make_plan, run_agent, workspace_path

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


@app.get("/api/workspaces")
async def list_workspaces():
    return sorted(p.name for p in WORKSPACES_ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))


@app.get("/api/files")
async def list_files(ws: str = Query("default")):
    return _tree(workspace_path(ws), 4, [0])


def _resolve_file(path: str, ws: str = "default") -> Path | None:
    w = workspace_path(ws)
    p = (w / path).resolve()
    if not str(p).startswith(str(w) + os.sep) or not p.is_file():
        return None
    return p


@app.get("/api/file")
async def read_file(path: str = Query(...), ws: str = Query("default")):
    p = _resolve_file(path, ws)
    if not p:
        return JSONResponse({"error": "invalid path"}, status_code=400)
    try:
        return {"path": str(p.relative_to(workspace_path(ws))), "content": p.read_text()[:100_000]}
    except UnicodeDecodeError:
        return JSONResponse({"error": "binary file"}, status_code=400)


class FileSave(BaseModel):
    path: str
    content: str
    ws: str = "default"


@app.post("/api/file")
async def save_file(f: FileSave):
    w = workspace_path(f.ws)
    p = (w / f.path).resolve()
    if not str(p).startswith(str(w) + os.sep):
        return JSONResponse({"error": "invalid path"}, status_code=400)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f.content)
    return {"ok": True, "path": str(p.relative_to(w)), "size": len(f.content)}


@app.get("/api/download")
async def download_file(path: str = Query(...), ws: str = Query("default")):
    p = _resolve_file(path, ws)
    if not p:
        return JSONResponse({"error": "invalid path"}, status_code=400)
    return FileResponse(p, filename=p.name)


@app.post("/api/upload")
async def upload(file: UploadFile, ws: str = Query("default")):
    name = Path(file.filename or "").name
    if not name:
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        return JSONResponse({"error": "file too large (max 20MB)"}, status_code=400)
    (workspace_path(ws) / name).write_bytes(data)
    return {"ok": True, "path": name, "size": len(data)}


@app.get("/api/git/log")
async def git_log(ws: str = Query("default")):
    w = workspace_path(ws)
    if not (w / ".git").exists():
        return {"commits": []}
    r = subprocess.run(
        ["git", "log", "--format=%h%x1f%s", "-20"],
        cwd=w, capture_output=True, text=True,
    )
    commits = [
        {"sha": sha, "msg": msg}
        for line in r.stdout.strip().splitlines() if line
        for sha, msg in [line.split("\x1f", 1)]
    ]
    return {"commits": commits}


@app.get("/api/git/diff")
async def git_diff(sha: str = Query(...), ws: str = Query("default")):
    w = workspace_path(ws)
    if not (w / ".git").exists() or not sha.replace("~", "").replace("^", "").isalnum():
        return JSONResponse({"error": "invalid"}, status_code=400)
    r = subprocess.run(
        ["git", "show", "--stat", "--patch", "--format=commit %h%n%s%n", sha],
        cwd=w, capture_output=True, text=True,
    )
    return {"diff": r.stdout[:12000]}


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


def _md_escape(text: str) -> str:
    return text.replace("```", "\\`\\`\\`")


@app.get("/api/export")
async def export_session(id: str = Query(...)):
    f = SESSIONS_DIR / f"{id}.json"
    if not f.exists():
        return JSONResponse({"error": "session not found"}, status_code=404)
    d = json.loads(f.read_text())
    lines = [
        f"# 🐚 MiniDevin — {d.get('title', 'Percakapan')}",
        f"_Diekspor {time.strftime('%Y-%m-%d %H:%M', time.localtime(d.get('updated', 0)))} "
        f"· workspace: `{d.get('workspace', 'default')}`_\n",
    ]
    for ev in d.get("events", []):
        t = ev["type"]
        if t == "user":
            lines.append(f"## 👤 User\n\n{ev['content']}\n")
        elif t == "message":
            lines.append(f"## 🐚 MiniDevin\n\n{ev['content']}\n")
        elif t == "thought":
            lines.append(f"> 💭 {ev['content']}\n")
        elif t == "plan":
            lines.append(f"## 🧠 Rencana\n\n{ev['content']}\n")
        elif t == "action":
            label = {"run_bash": "bash", "web_fetch": "url"}.get(ev["tool"], ev["tool"])
            body = ev["args"].get("command") or ev["args"].get("url") or json.dumps(ev["args"], ensure_ascii=False)
            lines.append(f"**🔧 {label}**\n\n```\n{_md_escape(body[:2000])}\n```\n")
        elif t == "observation":
            lines.append(f"<details><summary>📋 Observasi ({ev['tool']})</summary>\n\n```\n{_md_escape(ev['content'][:3000])}\n```\n</details>\n")
        elif t == "error":
            lines.append(f"**⚠️ Error:** {ev['content']}\n")
    md = "\n".join(lines)
    return Response(md, media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="minidevin-{id}.md"'})


SAVED_EVENTS = ("thought", "message", "action", "observation", "error", "plan")


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    session = None
    history: list = []
    cancel = asyncio.Event()
    current_task: asyncio.Task | None = None

    async def emit(event: dict):
        if session is not None and event["type"] in SAVED_EVENTS:
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
                               "updated": time.time(), "events": [], "history": [],
                               "workspace": data.get("workspace") or "default"}
                await websocket.send_text(json.dumps({
                    "type": "session", "session_id": session["id"],
                    "title": session["title"], "events": session["events"],
                    "workspace": session.get("workspace", "default"),
                }))

            elif mtype == "new_session":
                session = {"id": uuid.uuid4().hex[:12], "title": "Percakapan baru",
                           "updated": time.time(), "events": [], "history": [],
                           "workspace": data.get("workspace") or "default"}
                history = []
                await websocket.send_text(json.dumps({
                    "type": "session", "session_id": session["id"],
                    "title": session["title"], "events": [],
                    "workspace": session["workspace"],
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
                    plan_text = None
                    if data.get("plan"):
                        await emit({"type": "step", "step": 0})
                        plan_text = await make_plan(data["message"], CONFIG)
                        await emit({"type": "plan", "content": plan_text})

                    current_task = asyncio.create_task(
                        run_agent(data["message"], history, CONFIG, emit, cancel,
                                  plan=plan_text, workspace=session.get("workspace", "default"))
                    )
                    await current_task
                    history.append({"role": "user", "content": data["message"]})
                    history.append({"role": "assistant", "content": "(task processed)"})
                    history[:] = history[-20:]
                    session["history"] = history

                    snap = await asyncio.to_thread(
                        git_snapshot, f"task: {session['title']}",
                        workspace_path(session.get("workspace", "default")))
                    if "perubahan" not in snap and "tidak tersedia" not in snap:
                        await emit({"type": "observation", "tool": "git", "content": f"📸 Snapshot git:\n{snap}"})
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
