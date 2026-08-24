"""MiniDevin agent loop v7 — OpenHands-parity architecture.

Conversation loop: LLM emits Actions → Runtime executes → Observations
appended to the append-only EventStream. Supports multi-agent delegation,
confirmation mode, and an agent state machine.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import openai
from openai import AsyncOpenAI

from .agents import AGENTS, agent_descriptions, get_agent
from .events import EventStream
from .runtime import LocalRuntime

WORKSPACES_ROOT = Path(os.environ.get("MINIDEVIN_WORKSPACES", "/workspace/project/sandboxes")).resolve()
WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)
WORKSPACE = WORKSPACES_ROOT / "default"
WORKSPACE.mkdir(parents=True, exist_ok=True)

MAX_STEPS = 40
MAX_DELEGATION_DEPTH = 2


def workspace_path(name: str | None) -> Path:
    """Resolve a workspace name to its directory, guarding against traversal."""
    name = (name or "default").strip() or "default"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    p = (WORKSPACES_ROOT / safe).resolve()
    if not str(p).startswith(str(WORKSPACES_ROOT) + os.sep):
        p = WORKSPACE
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------- tool schemas ----------------

_TOOL_SCHEMAS: dict[str, dict] = {
    "run_bash": {
        "description": "Run a bash command in the workspace sandbox and return its output.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The bash command to execute."}},
            "required": ["command"],
        },
    },
    "write_file": {
        "description": "Write content to a file (path relative to the workspace). Creates parent directories.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    "edit_file": {
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
    "read_file": {
        "description": "Read the content of a file (path relative to the workspace).",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    "list_files": {
        "description": "List the directory tree of a path relative to the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory relative to workspace (default '.')."},
                "depth": {"type": "integer", "description": "Max depth (default 2)."},
            },
        },
    },
    "web_fetch": {
        "description": "Fetch a web page URL and return its text content (HTML stripped). Use for research.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "The URL to fetch."}},
            "required": ["url"],
        },
    },
    "set_api_key": {
        "description": "Update the LLM API key at runtime. Use when the user provides a new key in chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string"},
                "model": {"type": "string"},
                "base_url": {"type": "string"},
            },
            "required": ["api_key"],
        },
    },
    "delegate_to_agent": {
        "description": "Delegate a subtask to a specialist agent and get its final report.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Agent key: researcher | planner"},
                "task": {"type": "string", "description": "Clear description of the subtask."},
            },
            "required": ["agent", "task"],
        },
    },
    "finish": {
        "description": "Call when the task is complete. Provide a final summary for the user (Markdown allowed).",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
}


def tools_for(agent_key: str) -> list[dict]:
    allowed = get_agent(agent_key)["tools"]
    return [{"type": "function", "function": {"name": n, **_TOOL_SCHEMAS[n]}} for n in allowed if n in _TOOL_SCHEMAS]


GENERAL_PROMPT = """
Cara bekerja:
1. Berpikir singkat, lalu bertindak dengan tools yang tersedia.
2. Verifikasi hasil kerja Anda sebelum menyatakan selesai.
3. Jika tugas selesai, panggil tool `finish` dengan ringkasan (Markdown).

Aturan:
- Langkah kecil dan ter-verifikasi.
- Jangan minta user menjalankan perintah; lakukan sendiri dengan tools.
- Balas dengan bahasa yang sama dengan user.
"""

PLAN_PROMPT = """Anda adalah perencana (planner). Buat rencana langkah-demi-langkah yang ringkas
untuk menyelesaikan tugas user berikut. Jangan jalankan apa pun — hanya rencana bernomor.
Rencana akan dijalankan oleh agen coder.

Tugas: {task}

Rencana:"""

CONFIRMABLE_TOOLS = {"run_bash", "write_file", "edit_file"}


# ---------------- streaming completion ----------------

async def _create_completion(client: AsyncOpenAI, model: str, messages: list, tools: list, emit):
    """Stream a chat completion; returns (message_dict, usage_dict, full_content)."""

    async def _stream(**extra):
        stream = await client.chat.completions.create(
            model=model, messages=messages, tools=tools, tool_choice="auto", stream=True, **extra
        )
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
    if not shutil.which("git"):
        return "git tidak tersedia"
    opts = ["-c", "user.name=MiniDevin", "-c", "user.email=minidevin@localhost"]

    def run(*args):
        return subprocess.run(["git", *opts, *args], cwd=ws, capture_output=True, text=True)

    if not (ws / ".git").exists():
        run("init")
    run("add", "-A")
    status = run("status", "--porcelain")
    if not status.stdout.strip():
        return "tidak ada perubahan"
    commit = run("commit", "-m", message[:200])
    return (commit.stdout + commit.stderr).strip()


# ---------------- agent loop (Conversation) ----------------

async def run_agent(
    user_message: str,
    history: list,
    config: dict,
    emit,
    cancel: asyncio.Event,
    plan: str | None = None,
    workspace: str | None = None,
    stream: EventStream | None = None,
    runtime: LocalRuntime | None = None,
    agent_key: str = "coder",
    confirmation_mode: bool = False,
    confirm_hook=None,
    _depth: int = 0,
) -> dict:
    """OpenHands-style conversation loop over an EventStream + Runtime.
    Returns usage stats; events are appended to `stream` when provided."""
    ws = workspace_path(workspace)
    runtime = runtime or LocalRuntime(ws)
    persona = get_agent(agent_key)
    client = AsyncOpenAI(api_key=config["api_key"], base_url=config.get("base_url") or None)

    system = persona["prompt"].format(workspace=ws) + "\n" + GENERAL_PROMPT
    if agent_key == "coder":
        system += "\nAgen yang tersedia untuk delegasi:\n" + agent_descriptions()
    messages = [{"role": "system", "content": system}]
    if plan:
        messages.append({"role": "system", "content": f"Rencana yang harus Anda ikuti:\n{plan}"})
    messages += history
    messages.append({"role": "user", "content": user_message})

    tools = tools_for(agent_key)
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    async def set_state(state: str):
        await emit({"type": "state", "state": state, "agent": agent_key})
        if stream:
            stream.add("state", content=state, agent=agent_key)

    await set_state("running")

    for step in range(1, MAX_STEPS + 1):
        if cancel.is_set():
            await set_state("stopped")
            await emit({"type": "error", "content": "⏹️ Dihentikan oleh pengguna."})
            return {"steps": step, **usage}

        await emit({"type": "step", "step": step, "agent": agent_key})
        try:
            msg, step_usage, content = await _create_completion(client, config["model"], messages, tools, emit)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await set_state("error")
            await emit({"type": "error", "content": f"LLM error: {e}"})
            return {"steps": step, **usage}

        usage["prompt_tokens"] += step_usage["prompt_tokens"]
        usage["completion_tokens"] += step_usage["completion_tokens"]
        messages.append({k: v for k, v in msg.items() if v is not None})

        if content:
            await emit({"type": "thought", "content": content, "agent": agent_key})
            if stream:
                stream.add("thought", content=content, agent=agent_key)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            await set_state("finished")
            await emit({"type": "message", "content": content or "(no response)", "agent": agent_key})
            await emit({"type": "done", **usage})
            return {"steps": step, **usage}

        for call in tool_calls:
            if cancel.is_set():
                await set_state("stopped")
                await emit({"type": "error", "content": "⏹️ Dihentikan oleh pengguna."})
                return {"steps": step, **usage}

            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}

            # confirmation mode (OpenHands-style security gate)
            if confirmation_mode and name in CONFIRMABLE_TOOLS and confirm_hook:
                await set_state("awaiting_confirmation")
                approved = await confirm_hook({"tool": name, "args": args, "agent": agent_key})
                if not approved:
                    result = "User menolak aksi ini."
                    await emit({"type": "observation", "tool": name, "content": result, "agent": agent_key})
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                    continue
                await set_state("running")

            action_event = None
            if stream:
                action_event = stream.add("action", tool=name, args=args, agent=agent_key)
            await emit({"type": "action", "tool": name, "args": args, "agent": agent_key})

            # ---- execution ----
            if name == "finish":
                await set_state("finished")
                await emit({"type": "message", "content": args.get("summary", "Done."), "agent": agent_key})
                await emit({"type": "done", **usage})
                return {"steps": step, **usage}

            if name == "set_api_key":
                config["api_key"] = args.get("api_key", config["api_key"])
                if args.get("model"):
                    config["model"] = args["model"]
                if args.get("base_url"):
                    config["base_url"] = args["base_url"]
                result = "API key diperbarui."

            elif name == "delegate_to_agent":
                target = args.get("agent", "researcher")
                subtask = args.get("task", "")
                if _depth >= MAX_DELEGATION_DEPTH:
                    result = f"Error: batas kedalaman delegasi ({MAX_DELEGATION_DEPTH}) tercapai."
                elif target not in AGENTS or target == agent_key:
                    result = f"Error: agen '{target}' tidak tersedia."
                else:
                    await emit({"type": "delegation", "agent": target, "content": subtask})
                    if stream:
                        stream.add("delegation", content=subtask, agent=target)
                    sub = await run_agent(
                        subtask, [], config, emit, cancel,
                        workspace=workspace, stream=stream, runtime=runtime,
                        agent_key=target, confirmation_mode=confirmation_mode,
                        confirm_hook=confirm_hook, _depth=_depth + 1,
                    )
                    report = ""
                    if stream:
                        msgs = [e for e in stream.filter("message") if e.agent == target]
                        report = msgs[-1].content if msgs else "(sub-agen tidak menghasilkan laporan)"
                    usage["prompt_tokens"] += sub["prompt_tokens"]
                    usage["completion_tokens"] += sub["completion_tokens"]
                    result = f"Laporan dari {get_agent(target)['name']}:\n{report}"
                    await set_state("running")

            else:
                result = await asyncio.to_thread(runtime.execute, name, args)

            if stream:
                stream.add("observation", tool=name, content=result, agent=agent_key,
                           cause=action_event.id if action_event else "")
            await emit({"type": "observation", "tool": name, "content": result, "agent": agent_key})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    await set_state("error")
    await emit({"type": "error", "content": f"Stopped after {MAX_STEPS} steps (limit reached)."})
    return {"steps": MAX_STEPS, **usage}
