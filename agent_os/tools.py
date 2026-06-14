from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    label: str
    command: list[str]
    risk_level: str
    desk_scopes: list[str]
    requires_approved_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "label": self.label,
            "command": list(self.command),
            "risk_level": self.risk_level,
            "desk_scopes": list(self.desk_scopes),
            "requires_approved_action": self.requires_approved_action,
        }


def _astroq_command(*args: str) -> list[str]:
    local = Path(".venv/bin/astroq")
    executable = str(local) if local.exists() else "astroq"
    return [executable, *args]


DEFAULT_TOOLS: dict[str, ToolDescriptor] = {
    "astroq.health": ToolDescriptor(
        tool_id="astroq.health",
        label="Project health",
        command=_astroq_command("health", "--json"),
        risk_level="read_only",
        desk_scopes=["reporting", "engineering", "risk"],
    ),
    "astroq.lifecycle.check": ToolDescriptor(
        tool_id="astroq.lifecycle.check",
        label="Lifecycle readiness",
        command=_astroq_command("lifecycle", "check", "--json"),
        risk_level="read_only",
        desk_scopes=["risk", "reporting", "execution"],
    ),
    "astroq.data.status": ToolDescriptor(
        tool_id="astroq.data.status",
        label="Data status",
        command=_astroq_command("data", "status", "--json"),
        risk_level="read_only",
        desk_scopes=["data", "reporting"],
    ),
    "astroq.strategy.catalog": ToolDescriptor(
        tool_id="astroq.strategy.catalog",
        label="Strategy catalog",
        command=_astroq_command("strategy", "catalog", "--json"),
        risk_level="read_only",
        desk_scopes=["research", "reporting"],
    ),
    "astroq.data.repair": ToolDescriptor(
        tool_id="astroq.data.repair",
        label="Data repair",
        command=_astroq_command("data", "repair", "{table}", "--json"),
        risk_level="write_data",
        desk_scopes=["data"],
        requires_approved_action=True,
    ),
}


class AgentToolRegistry:
    """Fixed tool registry for agent runtime planning.

    The registry intentionally returns command arrays, not shell strings. Write-capable
    templated commands are unavailable until a later approved-action executor can bind
    parameters safely.
    """

    def __init__(self, tools: dict[str, ToolDescriptor] | None = None):
        self._tools = dict(tools or DEFAULT_TOOLS)

    def list(self) -> list[dict[str, Any]]:
        return [tool.to_dict() for tool in self._tools.values()]

    def get(self, tool_id: str) -> ToolDescriptor | None:
        return self._tools.get(tool_id)

    def command_for(self, tool_id: str, parameters: dict[str, Any] | None = None) -> list[str]:
        tool = self.get(tool_id)
        if tool is None:
            raise KeyError(f"Unknown agent tool: {tool_id}")
        if tool.requires_approved_action:
            raise ValueError(f"Agent tool {tool_id} requires explicit approval before binding parameters")
        if any(part.startswith("{") and part.endswith("}") for part in tool.command):
            raise ValueError(f"Agent tool {tool_id} has unbound command parameters")
        return list(tool.command)
