"""Append-only event stream — the single source of truth (OpenHands-style).

Every action, observation, message, and state change is an Event appended to
the stream. The stream is persisted as JSONL so sessions can be replayed.
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Event:
    type: str                      # user | message | thought | plan | action | observation | error | state | delegation
    content: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)
    agent: str = "coder"           # which agent produced this event
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    cause: str = ""                # id of the action event that caused this observation

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in ("", {}, None)}

    @staticmethod
    def from_dict(d: dict) -> "Event":
        known = {f for f in Event.__dataclass_fields__}
        return Event(**{k: v for k, v in d.items() if k in known})


class EventStream:
    """Append-only log of events with JSONL persistence and subscriber callbacks."""

    def __init__(self, persist_file: Path | None = None):
        self._events: list[Event] = []
        self._file = persist_file
        self._subscribers: list = []
        if persist_file and persist_file.exists():
            for line in persist_file.read_text().splitlines():
                if line.strip():
                    try:
                        self._events.append(Event.from_dict(json.loads(line)))
                    except Exception:
                        continue

    def subscribe(self, callback):
        """callback(event_dict) called for every new event (may be async)."""
        self._subscribers.append(callback)

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def append(self, event: Event) -> Event:
        self._events.append(event)
        if self._file:
            with self._file.open("a") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        for cb in self._subscribers:
            cb(event)
        return event

    def add(self, type: str, **kwargs) -> Event:
        return self.append(Event(type=type, **kwargs))

    def filter(self, *types: str) -> list[Event]:
        return [e for e in self._events if e.type in types]

    def to_llm_history(self, max_pairs: int = 10) -> list[dict]:
        """Rebuild a condensed conversation for the LLM from the event log."""
        history: list[dict] = []
        for e in self.filter("user", "message")[-max_pairs * 2:]:
            role = "user" if e.type == "user" else "assistant"
            history.append({"role": role, "content": e.content})
        return history
