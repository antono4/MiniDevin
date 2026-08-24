"""MiniDevin agent loop v3: tools + web_fetch + plan mode + git snapshots."""

import asyncio
import html
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

import openai
from openai import AsyncOpenAI

WORKSPACES_ROOT = Path(os.environ.get("MINIDEVIN_WORKSPACES", "/workspace/project/sandboxes")).resolve()
WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)
# Backward-compat: single default workspace
WORKSPACE = WORKSPACES_ROOT / "default"
WORKSPACE.mkdir(parents=True, exist_ok=True)


def workspace_path(name: str | None) -> Path:
    """Resolve a workspace name to its directory, guarding against traversal."""
    name = (name or "default").strip() or "default"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    p = (WORKSPACES_ROOT / safe).resolve()
    if not str(p).startswith(str(WORKSPACES_ROOT) + os.sep):
        p = WORKSPACE
    p.mkdir(parents=True, exist_ok=True)
    return p

MAX_STEPS = 40
BASH_TIMEOUT = 120
OUTPUT_LIMIT = 6000
TREE_LIMIT = 300
WEB_LIMIT = 4000

BLOCKED_SUBSTRINGS = ("rm -rf /", "rm -rf ~", "mkfs.", ":(){ :|:& };:", "dd if=/dev/zero of=/dev", "> /dev/sd")

SYSTEM_PROMPT = f"""Anda adalah MiniDevin, agen software engineer AI otonom (terinspirasi OpenDevin/OpenHands).
Anda membantu user membangun software dengan mengeksekusi aksi nyata di workspace sandbox.

Workspace: {WORKSPACE}

Cara bekerja:
1. Berpikir singkat, lalu bertindak dengan tools yang tersedia.
2. run_bash untuk perintah shell; write_file/edit_file untuk file; read_file/list_files untuk inspeksi; web_fetch untuk riset internet.
3. Verifikasi hasil kerja Anda: jalankan kode dan cek output sebelum menyatakan selesai.
4. Jika tugas selesai, panggil tool `finish` dengan ringkasan (Markdown).

Aturan:
- Langkah kecil dan ter-verifikasi.
- Jangan minta user menjalankan perintah; lakukan sendiri dengan tools.
- Ringkasan akhir dalam Markdown.
- Balas dengan bahasa yang sama dengan user.
"""

PLAN_PROMPT = """Anda adalah perencana (planner). Buat rencana langkah-demi-langkah yang ringkas
untuk menyelesaikan tugas user berikut. Jangan jalankan apa pun — hanya rencana bernomor.
Rencana akan dijalankan oleh agen coder.

Tugas: {task}

Rencana:"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run a bash command in the workspace sandbox and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute."}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (path relative to the workspace). Creates parent directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in a file. old_str must appear exactly once in the file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_str": {"type": "string", "description": "Exact text to replace (must be unique in the file)."},
                    "new_str": {"type": "string", "description": "Replacement text."},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file (path relative to the workspace).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the directory tree of a path relative to the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory relative to workspace (default '.')."},
                    "depth": {"type": "integer", "description": "Max depth (default 2)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a web page URL and return its text content (HTML stripped). Use for research.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Call when the task is complete. Provide a final summary for the user (Markdown allowed).",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


def _safe_path(path: str, ws: Path | None = None) -> Path:
    ws = ws or WORKSPACE
    p = (ws / path).resolve()
    if p != ws and not str(p).startswith(str(ws) + os.sep):
        raise ValueError(f"Path escapes workspace: {path}")
    return p


def _truncate(text: str) -> str:
    if len(text) > OUTPUT_LIMIT:
        return text[:OUTPUT_LIMIT] + f"\n... [truncated, {len(text)} chars total]"
    return text


def tool_run_bash(command: str, ws: Path | None = None) -> str:
    ws = ws or WORKSPACE
    if any(b in command for b in BLOCKED_SUBSTRINGS):
        return "Error: command blocked by safety guard."
    try:
        proc = subprocess.run(
            command, shell=True, cwd=ws, capture_output=True,
            text=True, timeout=BASH_TIMEOUT,
        )
        out = proc.stdout + proc.stderr
        return _truncate(out.strip() or f"(exit code {proc.returncode}, no output)")
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {BASH_TIMEOUT}s"


def tool_write_file(path: str, content: str, ws: Path | None = None) -> str:
    ws = ws or WORKSPACE
    try:
        p = _safe_path(path, ws)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {len(content)} chars to {p.relative_to(ws)}"
    except Exception as e:
        return f"Error: {e}"


def tool_edit_file(path: str, old_str: str, new_str: str, ws: Path | None = None) -> str:
    ws = ws or WORKSPACE
    try:
        p = _safe_path(path, ws)
        text = p.read_text()
        count = text.count(old_str)
        if count == 0:
            return "Error: old_str not found in file."
        if count > 1:
            return f"Error: old_str appears {count} times; it must be unique. Include more context."
        p.write_text(text.replace(old_str, new_str, 1))
        return f"Edited {p.relative_to(ws)}"
    except Exception as e:
        return f"Error: {e}"


def tool_read_file(path: str, ws: Path | None = None) -> str:
    try:
        return _truncate(_safe_path(path, ws or WORKSPACE).read_text())
    except Exception as e:
        return f"Error: {e}"


def tool_list_files(path: str = ".", depth: int = 2, ws: Path | None = None) -> str:
    ws = ws or WORKSPACE
    try:
        root = _safe_path(path, ws)
        if not root.is_dir():
            return f"Error: not a directory: {path}"
        lines, count = [], [0]

        def walk(d: Path, prefix: str, level: int):
            if level > depth or count[0] >= TREE_LIMIT:
                return
            entries = sorted(d.iterdir(), key=lambda e: (e.is_file(), e.name))
            for i, e in enumerate(entries):
                if count[0] >= TREE_LIMIT:
                    lines.append(prefix + "... [truncated]")
                    return
                if e.name.startswith(".") or e.name == "__pycache__":
                    continue
                count[0] += 1
                connector = "└── " if i == len(entries) - 1 else "├── "
                lines.append(prefix + connector + e.name + ("/" if e.is_dir() else ""))
                if e.is_dir():
                    walk(e, prefix + ("    " if i == len(entries) - 1 else "│   "), level + 1)

        lines.append(str(root.relative_to(ws)) if root != ws else ".")
        walk(root, "", 1)
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def tool_web_fetch(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MiniDevin/3.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(500_000).decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
        text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = html.unescape(re.sub(r"\s+", " ", text)).strip()
        return text[:WEB_LIMIT] or "(halaman kosong)"
    except Exception as e:
        return f"Error: {e}"


def execute_tool(name: str, args: dict, ws: Path | None = None) -> str:
    if name == "run_bash":
        return tool_run_bash(args["command"], ws)
    if name == "write_file":
        return tool_write_file(args["path"], args["content"], ws)
    if name == "edit_file":
        return tool_edit_file(args["path"], args["old_str"], args["new_str"], ws)
    if name == "read_file":
        return tool_read_file(args["path"], ws)
    if name == "list_files":
        return tool_list_files(args.get("path", "."), int(args.get("depth", 2)), ws)
    if name == "web_fetch":
        return tool_web_fetch(args["url"])
    if name == "finish":
        return "__FINISH__"
    return f"Error: unknown tool {name}"


async def _create_completion(client, model: str, messages: list, emit):
    """Stream a chat completion. Returns (message_dict, usage_dict, full_content).
    Falls back to non-streaming if the provider rejects streaming options."""
    kwargs = dict(messages=messages, tools=TOOLS, tool_choice="auto")

    async def _stream(**extra):
        stream = await client.chat.completions.create(model=model, stream=True, **kwargs, **extra)
        content_parts: list[str] = []
        tool_calls: dict[int, dict] = {}
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        async for chunk in stream:
            if chunk.usage:
                usage["prompt_tokens"] += chunk.usage.prompt_tokens or 0
                usage["completion_tokens"] += chunk.usage.completion_tokens or 0
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                await emit({"type": "thought_delta", "content": delta.content})
            for tc in delta.tool_calls or []:
                slot = tool_calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] += tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        message = {
            "role": "assistant",
            "content": "".join(content_parts) or None,
            "tool_calls": [
                {"id": t["id"] or f"call_{i}", "type": "function",
                 "function": {"name": t["name"], "arguments": t["arguments"]}}
                for i, t in sorted(tool_calls.items())
            ] or None,
        }
        return message, usage, message["content"]

    try:
        return await _stream(stream_options={"include_usage": True})
    except openai.BadRequestError as e:
        if "include_usage" in str(e) or "stream_options" in str(e):
            return await _stream()
        raise


async def make_plan(task: str, config: dict) -> str:
    client = AsyncOpenAI(api_key=config["api_key"], base_url=config.get("base_url") or None)
    resp = await client.chat.completions.create(
        model=config["model"],
        messages=[
            {"role": "system", "content": "Anda adalah planner ulang-tugas."},
            {"role": "user", "content": PLAN_PROMPT.format(task=task)},
        ],
    )
    return resp.choices[0].message.content or ""


def git_snapshot(message: str, ws: Path | None = None) -> str:
    ws = ws or WORKSPACE
    """Commit current workspace state. Returns result text."""
    if not shutil.which("git"):
        return "git tidak tersedia"
    env = dict(os.environ)
    opts = ["-c", "user.name=MiniDevin", "-c", "user.email=minidevin@localhost"]

    def run(*args):
        return subprocess.run(["git", *opts, *args], cwd=ws, capture_output=True, text=True, env=env)

    if not (ws / ".git").exists():
        run("init")
        run("add", "-A")
    status = run("status", "--porcelain")
    if not status.stdout.strip():
        return "tidak ada perubahan"
    run("add", "-A")
    commit = run("commit", "-m", message[:200])
    return (commit.stdout + commit.stderr).strip()


async def run_agent(user_message: str, history: list, config: dict, emit, cancel: asyncio.Event,
                    plan: str | None = None, workspace: str | None = None) -> dict:
    """Run the agent loop. `emit` sends event dicts to the client. Returns usage stats."""
    ws = workspace_path(workspace)
    client = AsyncOpenAI(api_key=config["api_key"], base_url=config.get("base_url") or None)
    messages = [{"role": "system", "content": SYSTEM_PROMPT.replace(str(WORKSPACE), str(ws))}]
    if plan:
        messages.append({"role": "system", "content": f"Rencana yang harus Anda ikuti:\n{plan}"})
    messages += history
    messages.append({"role": "user", "content": user_message})
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for step in range(1, MAX_STEPS + 1):
        if cancel.is_set():
            await emit({"type": "error", "content": "⏹️ Dihentikan oleh pengguna."})
            return {"steps": step, **usage}

        await emit({"type": "step", "step": step})
        try:
            msg, step_usage, content = await _create_completion(client, config["model"], messages, emit)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await emit({"type": "error", "content": f"LLM error: {e}"})
            return {"steps": step, **usage}

        usage["prompt_tokens"] += step_usage["prompt_tokens"]
        usage["completion_tokens"] += step_usage["completion_tokens"]
        messages.append({k: v for k, v in msg.items() if v is not None})

        if content:
            await emit({"type": "thought", "content": content})

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            await emit({"type": "message", "content": content or "(no response)"})
            await emit({"type": "done", **usage})
            return {"steps": step, **usage}

        for call in tool_calls:
            if cancel.is_set():
                await emit({"type": "error", "content": "⏹️ Dihentikan oleh pengguna."})
                return {"steps": step, **usage}

            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            await emit({"type": "action", "tool": name, "args": args})

            result = await asyncio.to_thread(execute_tool, name, args, ws)
            if result == "__FINISH__":
                await emit({"type": "message", "content": args.get("summary", "Done.")})
                await emit({"type": "done", **usage})
                return {"steps": step, **usage}

            await emit({"type": "observation", "tool": name, "content": result})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    await emit({"type": "error", "content": f"Stopped after {MAX_STEPS} steps (limit reached)."})
    return {"steps": MAX_STEPS, **usage}
