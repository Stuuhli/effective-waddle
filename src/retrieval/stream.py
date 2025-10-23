"""Utilities for structured chat streaming events."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

StreamEventType = Literal["status", "token", "context", "citations", "done", "error"]


@dataclass(slots=True)
class StreamEvent:
    """Structured payload emitted during chat streaming."""

    type: StreamEventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type, "timestamp": self.timestamp.isoformat()}
        payload.update(self.data)
        return payload

    @classmethod
    def status(cls, *, stage: str, message: str) -> "StreamEvent":
        return cls("status", {"stage": stage, "message": message})

    @classmethod
    def token(cls, *, text: str) -> "StreamEvent":
        return cls("token", {"text": text})

    @classmethod
    def context(cls, *, chunks: list[dict[str, Any]]) -> "StreamEvent":
        return cls("context", {"chunks": chunks})

    @classmethod
    def citations(cls, *, citations: list[dict[str, Any]]) -> "StreamEvent":
        return cls("citations", {"citations": citations})

    @classmethod
    def done(cls) -> "StreamEvent":
        return cls("done", {})

    @classmethod
    def error(cls, *, message: str) -> "StreamEvent":
        return cls("error", {"message": message})


__all__ = ["StreamEvent", "StreamEventType"]
