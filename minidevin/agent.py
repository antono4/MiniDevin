"""MiniDevin agent loop: LLM + tools (bash, file read/write, finish)."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

from openai import AsyncOpenAI

WORKSPACE = Path(os.environ.get("MINIDEVIN_WORKSPACE", "/workspace/project/sandbox")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)

MAX_STEPS = 30
BASH_TIMEOUT = 120
OUTPUT_LIMIT = 6000

SYSTEM_PROMPT = f"""You are MiniDevin, an autonomous AI software engineer (inspired by OpenDevin/OpenHands).
You help the user build software by executing real actions in a sandboxed workspace.

Workspace directory: {WORKSPACE}

How you work:
1. Think briefly about the task, then act using the available tools.
2. Use run_bash to run shell commands (install packages, run scripts, inspect output).
3. Use write_file / read_file to create and inspect files. Paths are relative to the workspace.
4. Verify your work: run the code you write and check the output before declaring completion.
5. When the task is fully done, call the `finish` tool with a summary of what you built.

Rules:
- Always prefer small, verifiable steps.
- Never ask the user to run commands for you; do it yourself with the tools.
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
            "name": "finish",
            "description": "Call when the task is complete. Provide a final summary for the user.",
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
    if not str(p).startswith(str(WORKSPACE)):
        raise ValueError(f"Path escapes workspace: {path}")
    return p


def _truncate(text: str) -> str:
    if len(text) > OUTPUT_LIMIT:
        return text[:OUTPUT_LIMIT] + f"\n... [truncated, {len(text)} chars total]"
    return text


def tool_run_bash(command: str) -> str:
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


def tool_read_file(path: str) -> str:
    try:
        return _truncate(_safe_path(path).read_text())
    except Exception as e:
        return f"Error: {e}"


def execute_tool(name: str, args: dict) -> str:
    if name == "run_bash":
        return tool_run_bash(args["command"])
    if name == "write_file":
        return tool_write_file(args["path"], args["content"])
    if name == "read_file":
        return tool_read_file(args["path"])
    if name == "finish":
        return "__FINISH__"
    return f"Error: unknown tool {name}"


async def run_agent(user_message: str, history: list, config: dict, emit) -> None:
    """Run the agent loop. `emit` is an async callable sending event dicts to the client."""
    client = AsyncOpenAI(api_key=config["api_key"], base_url=config.get("base_url") or None)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    messages.append({"role": "user", "content": user_message})

    for step in range(MAX_STEPS):
        try:
            resp = await client.chat.completions.create(
                model=config["model"], messages=messages, tools=TOOLS, tool_choice="auto",
            )
        except Exception as e:
            await emit({"type": "error", "content": f"LLM error: {e}"})
            return

        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if msg.content:
            await emit({"type": "thought", "content": msg.content})

        if not msg.tool_calls:
            await emit({"type": "message", "content": msg.content or "(no response)"})
            return

        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            await emit({"type": "action", "tool": name, "args": args})

            result = await asyncio.to_thread(execute_tool, name, args)
            if result == "__FINISH__":
                await emit({"type": "message", "content": args.get("summary", "Done.")})
                await emit({"type": "done"})
                return

            await emit({"type": "observation", "tool": name, "content": result})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    await emit({"type": "error", "content": f"Stopped after {MAX_STEPS} steps (limit reached)."})
