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

from .agent import WORKSPACES_ROOT, git_snapshot, make_plan, run_agent, workspace_path
from .agents import AGENTS
from .events import EventStream
from .runtime import LocalRuntime

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
        "agents": [{"key": k, "name": v["name"], "icon": v["icon"], "description": v["description"]}
                   for k, v in AGENTS.items()],
    }


@app.get("/api/events")
async def get_events(id: str = Query(...)):
    f = SESSIONS_DIR / f"{id}.jsonl"
    if not f.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    out = []
    for line in f.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return {"events": out}


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


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    f = SESSIONS_DIR / f"{sid}.json"
    if not f.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    f.unlink()
    return {"ok": True}


@app.get("/api/sessions/search")
async def search_sessions(q: str = Query("")):
    q = q.lower().strip()
    out = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if not q or q in d.get("title", "").lower():
            out.append({"id": d["id"], "title": d.get("title", "Untitled"), "updated": d.get("updated", 0)})
            continue
        for ev in d.get("events", []):
            if q in str(ev.get("content", "")).lower():
                out.append({"id": d["id"], "title": d.get("title", "Untitled"), "updated": d.get("updated", 0)})
                break
    return out[:50]


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


SAVED_EVENTS = ("thought", "message", "action", "observation", "error", "plan", "delegation")


def _new_session(ws_name: str) -> dict:
    return {"id": uuid.uuid4().hex[:12], "title": "Percakapan baru",
            "updated": time.time(), "events": [], "history": [],
            "workspace": ws_name or "default"}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    session = None
    history: list = []
    cancel = asyncio.Event()
    current_task: asyncio.Task | None = None
    confirm_queue: asyncio.Queue = asyncio.Queue()
    confirmation_mode = False

    async def emit(event: dict):
        if session is not None and event["type"] in SAVED_EVENTS:
            session["events"].append(event)
        await websocket.send_text(json.dumps(event))

    async def confirm_hook(action: dict) -> bool:
        """Ask the user to approve an action (confirmation mode)."""
        await websocket.send_text(json.dumps({"type": "confirm", **action}))
        try:
            return bool(await asyncio.wait_for(confirm_queue.get(), timeout=300))
        except asyncio.TimeoutError:
            return False

    try:
        while True:
            data = json.loads(await websocket.receive_text())
            mtype = data.get("type")

            if mtype == "confirm":
                confirm_queue.put_nowait(bool(data.get("approved")))
                continue

            if mtype == "set_confirmation":
                confirmation_mode = bool(data.get("enabled"))
                await websocket.send_text(json.dumps({"type": "confirmation_mode", "enabled": confirmation_mode}))
                continue

            if mtype == "init":
                sid = data.get("session_id")
                f = SESSIONS_DIR / f"{sid}.json" if sid else None
                if f and f.exists():
                    session = json.loads(f.read_text())
                    history = session.get("history", [])
                else:
                    session = _new_session(data.get("workspace"))
                await websocket.send_text(json.dumps({
                    "type": "session", "session_id": session["id"],
                    "title": session["title"], "events": session["events"],
                    "workspace": session.get("workspace", "default"),
                }))

            elif mtype == "new_session":
                session = _new_session(data.get("workspace"))
                history = []
                await websocket.send_text(json.dumps({
                    "type": "session", "session_id": session["id"],
                    "title": session["title"], "events": [],
                    "workspace": session["workspace"],
                }))

            elif mtype == "stop":
                cancel.set()
                confirm_queue.put_nowait(False)
                if current_task and not current_task.done():
                    current_task.cancel()

            elif mtype == "chat":
                if session is None:
                    continue
                msg = data["message"].strip()
                if msg == "/reset":
                    history.clear()
                    session["history"] = []
                    session["events"] = []
                    _save_session(session)
                    (SESSIONS_DIR / f"{session['id']}.jsonl").unlink(missing_ok=True)
                    await websocket.send_text(json.dumps({
                        "type": "session", "session_id": session["id"],
                        "title": session["title"], "events": [],
                        "workspace": session.get("workspace", "default"),
                    }))
                    await emit({"type": "message", "content": "🔄 Konteks percakapan direset. Silakan mulai dari awal."})
                    continue
                if msg == "/confirm":
                    confirmation_mode = not confirmation_mode
                    await websocket.send_text(json.dumps({"type": "confirmation_mode", "enabled": confirmation_mode}))
                    await emit({"type": "message", "content": f"🛡️ Mode konfirmasi {'AKTIF — setiap aksi bash/tulis/edit akan meminta persetujuan Anda.' if confirmation_mode else 'nonaktif.'}"})
                    continue
                if not CONFIG["api_key"]:
                    await emit({"type": "error", "content": "LLM belum dikonfigurasi. Klik ⚙️ Settings dan masukkan API key Anda."})
                    continue
                plan_flag = bool(data.get("plan"))
                if msg.startswith("/plan "):
                    plan_flag = True
                    msg = msg[6:]
                if msg.startswith("/web "):
                    msg = ("Gunakan tool web_fetch untuk meneliti URL/topik berikut, lalu jawab "
                           "pertanyaan user berdasarkan hasilnya. Jangan tulis file apa pun kecuali diminta. "
                           "Topik: " + msg[5:])
                elif msg.startswith("/run "):
                    msg = ("Jalankan perintah bash berikut persis seperti tertulis dengan run_bash, "
                           "lalu laporkan outputnya apa adanya: " + msg[5:])
                if session["title"] == "Percakapan baru":
                    session["title"] = msg[:60]
                session["events"].append({"type": "user", "content": data["message"]})

                # OpenHands-style: append-only event stream persisted as JSONL
                stream = EventStream(SESSIONS_DIR / f"{session['id']}.jsonl")
                stream.add("user", content=msg)
                runtime = LocalRuntime(workspace_path(session.get("workspace", "default")))
                cancel = asyncio.Event()
                try:
                    plan_text = None
                    if plan_flag:
                        await emit({"type": "step", "step": 0})
                        plan_text = await make_plan(msg, CONFIG)
                        await emit({"type": "plan", "content": plan_text})
                        stream.add("plan", content=plan_text)

                    current_task = asyncio.create_task(
                        run_agent(msg, history, CONFIG, emit, cancel,
                                  plan=plan_text, workspace=session.get("workspace", "default"),
                                  stream=stream, runtime=runtime,
                                  confirmation_mode=confirmation_mode,
                                  confirm_hook=confirm_hook if confirmation_mode else None)
                    )
                    await current_task
                    history.append({"role": "user", "content": msg})
                    history.append({"role": "assistant", "content": "(task processed)"})
                    history[:] = history[-20:]
                    session["history"] = history

                    snap = await asyncio.to_thread(
                        git_snapshot, f"task: {session['title']}", runtime.workspace)
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
