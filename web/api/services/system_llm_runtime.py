from __future__ import annotations

from typing import Any

from data.llm.runtime_profile import RuntimeProfileError
from data.llm.runtime_profile import clear_active_profile
from data.llm.runtime_profile import discover_provider_models
from data.llm.runtime_profile import effective_profile
from data.llm.runtime_profile import runtime_options
from data.llm.runtime_profile import save_active_profile
from data.llm.runtime_profile import validate_profile


def llm_runtime_payload() -> dict[str, Any]:
    options = runtime_options()
    return {
        "profile": effective_profile("agent_response"),
        "providers": options["providers"],
        "controlled_use_cases": options["controlled_use_cases"],
    }


def update_llm_runtime_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if bool(payload.get("reset")):
        clear_active_profile()
        return llm_runtime_payload()

    provider = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "").strip()
    reasoning_mode = str(payload.get("reasoning_mode") or "default").strip() or "default"
    validate_profile(provider=provider, model=model, reasoning_mode=reasoning_mode)
    save_active_profile(provider=provider, model=model, reasoning_mode=reasoning_mode)
    return llm_runtime_payload()


def discover_llm_provider_models_payload(provider: str) -> dict[str, Any]:
    discovery = discover_provider_models(provider)
    return {
        "discovery": discovery,
        "runtime": llm_runtime_payload(),
    }
