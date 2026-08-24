"""MiniDevin agent loop v2: LLM + tools, cancellation, usage tracking."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

from openai import AsyncOpenAI

WORKSPACE = Path(os.environ.get("MINIDEVIN_WORKSPACE", "/workspace/project/sandbox")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)

MAX_STEPS = 40
BASH_TIMEOUT = 120
OUTPUT_LIMIT = 6000
TREE_LIMIT = 300

BLOCKED_SUBSTRINGS = ("rm -rf /", "rm -rf ~", "mkfs.", ":(){ :|:& };:", "dd if=/dev/zero of=/dev", "> /dev/sd")

SYSTEM_PROMPT = f"""You are MiniDevin, an autonomous AI software engineer (inspired by OpenDevin/OpenHands).
You help the user build software by executing real actions in a sandboxed workspace.

Workspace directory: {WORKSPACE}

How you work:
1. Think briefly about the task, then act using the available tools.
2. Use run_bash to run shell commands (install packages, run scripts, inspect output).
3. Use write_file to create files and edit_file for precise modifications. Use read_file and list_files to inspect the workspace.
4. Verify your work: run the code you write and check the output before declaring completion.
5. When the task is fully done, call the `finish` tool with a summary of what you built.

Rules:
- Always prefer small, verifiable steps.
- Never ask the user to run commands for you; do it yourself with the tools.
- Format your final summary in Markdown.
- Reply in the same language the user uses.
"""

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


def _safe_path(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    if p != WORKSPACE and not str(p).startswith(str(WORKSPACE) + os.sep):
        raise ValueError(f"Path escapes workspace: {path}")
    return p


def _truncate(text: str) -> str:
    if len(text) > OUTPUT_LIMIT:
        return text[:OUTPUT_LIMIT] + f"\n... [truncated, {len(text)} chars total]"
    return text


def tool_run_bash(command: str) -> str:
    if any(b in command for b in BLOCKED_SUBSTRINGS):
        return "Error: command blocked by safety guard."
    try:
        proc = subprocess.run(
            command, shell=True, cwd=WORKSPACE, capture_output=True,
            text=True, timeout=BASH_TIMEOUT,
        )
        out = proc.stdout + proc.stderr
        return _truncate(out.strip() or f"(exit code {proc.returncode}, no output)")
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {BASH_TIMEOUT}s"


def tool_write_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {len(content)} chars to {p.relative_to(WORKSPACE)}"
    except Exception as e:
        return f"Error: {e}"


def tool_edit_file(path: str, old_str: str, new_str: str) -> str:
    try:
        p = _safe_path(path)
        text = p.read_text()
        count = text.count(old_str)
        if count == 0:
            return "Error: old_str not found in file."
        if count > 1:
            return f"Error: old_str appears {count} times; it must be unique. Include more context."
        p.write_text(text.replace(old_str, new_str, 1))
        return f"Edited {p.relative_to(WORKSPACE)}"
    except Exception as e:
        return f"Error: {e}"


def tool_read_file(path: str) -> str:
    try:
        return _truncate(_safe_path(path).read_text())
    except Exception as e:
        return f"Error: {e}"


def tool_list_files(path: str = ".", depth: int = 2) -> str:
    try:
        root = _safe_path(path)
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

        lines.append(str(root.relative_to(WORKSPACE)) if root != WORKSPACE else ".")
        walk(root, "", 1)
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def execute_tool(name: str, args: dict) -> str:
    if name == "run_bash":
        return tool_run_bash(args["command"])
    if name == "write_file":
        return tool_write_file(args["path"], args["content"])
    if name == "edit_file":
        return tool_edit_file(args["path"], args["old_str"], args["new_str"])
    if name == "read_file":
        return tool_read_file(args["path"])
    if name == "list_files":
        return tool_list_files(args.get("path", "."), int(args.get("depth", 2)))
    if name == "finish":
        return "__FINISH__"
    return f"Error: unknown tool {name}"


async def run_agent(user_message: str, history: list, config: dict, emit, cancel: asyncio.Event) -> dict:
    """Run the agent loop. `emit` is an async callable sending event dicts to the client.
    Returns a stats dict (steps, tokens) for session bookkeeping."""
    client = AsyncOpenAI(api_key=config["api_key"], base_url=config.get("base_url") or None)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    messages.append({"role": "user", "content": user_message})
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for step in range(1, MAX_STEPS + 1):
        if cancel.is_set():
            await emit({"type": "error", "content": "⏹️ Dihentikan oleh pengguna."})
            return {"steps": step, **usage}

        await emit({"type": "step", "step": step})
        try:
            resp = await client.chat.completions.create(
                model=config["model"], messages=messages, tools=TOOLS, tool_choice="auto",
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await emit({"type": "error", "content": f"LLM error: {e}"})
            return {"steps": step, **usage}

        if resp.usage:
            usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
            usage["completion_tokens"] += resp.usage.completion_tokens or 0

        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if msg.content:
            await emit({"type": "thought", "content": msg.content})

        if not msg.tool_calls:
            await emit({"type": "message", "content": msg.content or "(no response)"})
            await emit({"type": "done", **usage})
            return {"steps": step, **usage}

        for call in msg.tool_calls:
            if cancel.is_set():
                await emit({"type": "error", "content": "⏹️ Dihentikan oleh pengguna."})
                return {"steps": step, **usage}

            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            await emit({"type": "action", "tool": name, "args": args})

            result = await asyncio.to_thread(execute_tool, name, args)
            if result == "__FINISH__":
                await emit({"type": "message", "content": args.get("summary", "Done.")})
                await emit({"type": "done", **usage})
                return {"steps": step, **usage}

            await emit({"type": "observation", "tool": name, "content": result})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    await emit({"type": "error", "content": f"Stopped after {MAX_STEPS} steps (limit reached)."})
    return {"steps": MAX_STEPS, **usage}
