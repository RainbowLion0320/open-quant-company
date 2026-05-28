from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    OK = 0
    FAILED = 1
    USAGE = 2


@dataclass(frozen=True)
class CliResult:
    ok: bool
    command: str
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "data": self.data,
            "message": self.message,
            "errors": self.errors,
        }

    def render_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    def render_text(self) -> str:
        status = "OK" if self.ok else "ERROR"
        lines = [f"{status}: {self.message or self.command}"]
        for key, value in self.data.items():
            lines.append(f"{key}: {value}")
        for err in self.errors:
            lines.append(f"error: {err}")
        return "\n".join(lines)
