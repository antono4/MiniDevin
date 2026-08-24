"""Execution runtime — the Workspace layer (OpenHands-style).

The runtime owns everything about *where* actions execute: the working
directory, safety guards, and observation generation. Agents never touch
the filesystem directly; they go through the runtime.
"""

import html
import os
import re
import subprocess
import urllib.request
from pathlib import Path

BASH_TIMEOUT = 120
OUTPUT_LIMIT = 6000
TREE_LIMIT = 300
WEB_LIMIT = 4000

BLOCKED_SUBSTRINGS = ("rm -rf /", "rm -rf ~", "mkfs.", ":(){ :|:& };:", "dd if=/dev/zero of=/dev", "> /dev/sd")


class LocalRuntime:
    """Executes actions in a local workspace directory."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ---- path safety ----
    def safe_path(self, path: str) -> Path:
        p = (self.workspace / path).resolve()
        if p != self.workspace and not str(p).startswith(str(self.workspace) + os.sep):
            raise ValueError(f"Path escapes workspace: {path}")
        return p

    @staticmethod
    def _truncate(text: str) -> str:
        if len(text) > OUTPUT_LIMIT:
            return text[:OUTPUT_LIMIT] + f"\n... [truncated, {len(text)} chars total]"
        return text

    # ---- actions → observations ----
    def run_bash(self, command: str) -> str:
        if any(b in command for b in BLOCKED_SUBSTRINGS):
            return "Error: command blocked by safety guard."
        try:
            proc = subprocess.run(
                command, shell=True, cwd=self.workspace, capture_output=True,
                text=True, timeout=BASH_TIMEOUT,
            )
            out = proc.stdout + proc.stderr
            return self._truncate(out.strip() or f"(exit code {proc.returncode}, no output)")
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {BASH_TIMEOUT}s"

    def write_file(self, path: str, content: str) -> str:
        try:
            p = self.safe_path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Wrote {len(content)} chars to {p.relative_to(self.workspace)}"
        except Exception as e:
            return f"Error: {e}"

    def edit_file(self, path: str, old_str: str, new_str: str) -> str:
        try:
            p = self.safe_path(path)
            text = p.read_text()
            count = text.count(old_str)
            if count == 0:
                return "Error: old_str not found in file."
            if count > 1:
                return f"Error: old_str appears {count} times; it must be unique. Include more context."
            p.write_text(text.replace(old_str, new_str, 1))
            return f"Edited {p.relative_to(self.workspace)}"
        except Exception as e:
            return f"Error: {e}"

    def read_file(self, path: str) -> str:
        try:
            return self._truncate(self.safe_path(path).read_text())
        except Exception as e:
            return f"Error: {e}"

    def list_files(self, path: str = ".", depth: int = 2) -> str:
        try:
            root = self.safe_path(path)
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

            lines.append(str(root.relative_to(self.workspace)) if root != self.workspace else ".")
            walk(root, "", 1)
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def web_fetch(url: str) -> str:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MiniDevin/7.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read(500_000).decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
            text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
            text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = html.unescape(re.sub(r"\s+", " ", text)).strip()
            return text[:WEB_LIMIT] or "(halaman kosong)"
        except Exception as e:
            return f"Error: {e}"

    def execute(self, name: str, args: dict) -> str:
        """Route an action to its execution method. Returns observation text."""
        if name == "run_bash":
            return self.run_bash(args.get("command", ""))
        if name == "write_file":
            return self.write_file(args.get("path", ""), args.get("content", ""))
        if name == "edit_file":
            return self.edit_file(args.get("path", ""), args.get("old_str", ""), args.get("new_str", ""))
        if name == "read_file":
            return self.read_file(args.get("path", ""))
        if name == "list_files":
            return self.list_files(args.get("path", "."), int(args.get("depth", 2)))
        if name == "web_fetch":
            return self.web_fetch(args.get("url", ""))
        return f"Error: unknown runtime action {name}"
