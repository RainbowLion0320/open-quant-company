from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field
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
    parameter_patterns: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "label": self.label,
            "command": list(self.command),
            "risk_level": self.risk_level,
            "desk_scopes": list(self.desk_scopes),
            "requires_approved_action": self.requires_approved_action,
            "parameter_patterns": dict(self.parameter_patterns),
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
        desk_scopes=["portfolio", "risk", "reporting", "execution"],
    ),
    "astroq.execution.dry_run": ToolDescriptor(
        tool_id="astroq.execution.dry_run",
        label="Execution dry-run",
        command=_astroq_command("execution", "dry-run", "--json"),
        risk_level="dry_run",
        desk_scopes=["portfolio", "execution", "risk"],
    ),
    "astroq.agent.live.readiness": ToolDescriptor(
        tool_id="astroq.agent.live.readiness",
        label="MiniQMT/QMT live readiness",
        command=_astroq_command("agent", "live", "readiness", "--json"),
        risk_level="read_only",
        desk_scopes=["execution"],
    ),
    "astroq.architecture.ast": ToolDescriptor(
        tool_id="astroq.architecture.ast",
        label="AST intelligence",
        command=_astroq_command("architecture", "ast", "--json"),
        risk_level="read_only",
        desk_scopes=["engineering"],
    ),
    "astroq.test.design": ToolDescriptor(
        tool_id="astroq.test.design",
        label="Test design intelligence",
        command=_astroq_command("test", "design", "--json"),
        risk_level="read_only",
        desk_scopes=["engineering"],
    ),
    "astroq.docs.check": ToolDescriptor(
        tool_id="astroq.docs.check",
        label="Documentation hygiene check",
        command=_astroq_command("docs", "check", "--json"),
        risk_level="read_only",
        desk_scopes=["engineering"],
    ),
    "astroq.data.status": ToolDescriptor(
        tool_id="astroq.data.status",
        label="Data status",
        command=_astroq_command("data", "status", "--json"),
        risk_level="read_only",
        desk_scopes=["data", "reporting"],
    ),
    "astroq.data.sources": ToolDescriptor(
        tool_id="astroq.data.sources",
        label="Data source capabilities",
        command=_astroq_command("data", "sources", "--json"),
        risk_level="read_only",
        desk_scopes=["data"],
    ),
    "astroq.data.sources.diff_registry": ToolDescriptor(
        tool_id="astroq.data.sources.diff_registry",
        label="Data source capability registry diff",
        command=_astroq_command("data", "sources", "diff-registry", "--json"),
        risk_level="read_only",
        desk_scopes=["data"],
    ),
    "astroq.strategy.catalog": ToolDescriptor(
        tool_id="astroq.strategy.catalog",
        label="Strategy catalog",
        command=_astroq_command("strategy", "catalog", "--json"),
        risk_level="read_only",
        desk_scopes=["research", "portfolio", "reporting"],
    ),
    "astroq.strategy.compete": ToolDescriptor(
        tool_id="astroq.strategy.compete",
        label="Strategy competition evidence",
        command=_astroq_command("strategy", "compete", "--json"),
        risk_level="read_only",
        desk_scopes=["research", "portfolio"],
    ),
    "astroq.backtest.run.dry_run": ToolDescriptor(
        tool_id="astroq.backtest.run.dry_run",
        label="Backtest dry run",
        command=_astroq_command("backtest", "run", "--dry-run", "--json"),
        risk_level="dry_run",
        desk_scopes=["research"],
    ),
    "astroq.agent.report.daily": ToolDescriptor(
        tool_id="astroq.agent.report.daily",
        label="Daily CEO report",
        command=_astroq_command("agent", "report", "daily", "--session", "{session_id}", "--json"),
        risk_level="write_artifact",
        desk_scopes=["reporting"],
        requires_approved_action=True,
        parameter_patterns={"session_id": r"^(agt_sess|ses)_[A-Za-z0-9]+$"},
    ),
    "astroq.data.repair": ToolDescriptor(
        tool_id="astroq.data.repair",
        label="Data repair",
        command=_astroq_command("data", "repair", "{table}", "--json"),
        risk_level="write_data",
        desk_scopes=["data"],
        requires_approved_action=True,
        parameter_patterns={"table": r"^[A-Za-z][A-Za-z0-9_]*$"},
    ),
    "astroq.data.repair.dry_run": ToolDescriptor(
        tool_id="astroq.data.repair.dry_run",
        label="Data repair dry run",
        command=_astroq_command("data", "repair", "{table}", "--dry-run", "--json"),
        risk_level="dry_run",
        desk_scopes=["data"],
        parameter_patterns={"table": r"^[A-Za-z][A-Za-z0-9_]*$"},
    ),
}


class AgentToolRegistry:
    """Fixed tool registry for agent runtime planning.

    The registry intentionally returns command arrays, not shell strings. Write-capable
    templated commands require an approved action and bind parameters only through
    tool-declared patterns.
    """

    def __init__(self, tools: dict[str, ToolDescriptor] | None = None):
        self._tools = dict(tools or DEFAULT_TOOLS)

    def list(self) -> list[dict[str, Any]]:
        return [tool.to_dict() for tool in self._tools.values()]

    def get(self, tool_id: str) -> ToolDescriptor | None:
        return self._tools.get(tool_id)

    def command_for(self, tool_id: str, parameters: dict[str, Any] | None = None, *, approved: bool = False) -> list[str]:
        tool = self.get(tool_id)
        if tool is None:
            raise KeyError(f"Unknown agent tool: {tool_id}")
        if tool.requires_approved_action and not approved:
            raise ValueError(f"Agent tool {tool_id} requires explicit approval before binding parameters")
        params = parameters or {}
        command: list[str] = []
        for part in tool.command:
            if part.startswith("{") and part.endswith("}"):
                name = part[1:-1]
                if name not in params:
                    raise ValueError(f"Agent tool {tool_id} missing command parameter: {name}")
                value = str(params[name]).strip()
                pattern = tool.parameter_patterns.get(name)
                if not value or not pattern or not re.fullmatch(pattern, value):
                    raise ValueError(f"Agent tool {tool_id} invalid command parameter: {name}")
                command.append(value)
            else:
                command.append(part)
        return command
