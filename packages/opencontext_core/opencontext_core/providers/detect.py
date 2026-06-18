"""Ambient provider detection — reads the environment, returns the best available provider."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class DetectedProvider:
    name: str  # anthropic | openai | openrouter | ollama | mock
    api_key: str  # empty string for local/mock
    model: str  # sensible default for this provider
    source: str  # env_var | ollama_local | fallback


_ENV_MAP = [
    ("ANTHROPIC_API_KEY", "anthropic", "claude-sonnet-4-6"),
    ("OPENAI_API_KEY", "openai", "gpt-4o"),
    ("OPENROUTER_API_KEY", "openrouter", "anthropic/claude-sonnet-4-6"),
    ("GEMINI_API_KEY", "google", "gemini-2.0-flash"),
    ("MISTRAL_API_KEY", "mistral", "mistral-large-latest"),
]


def detect_provider() -> DetectedProvider:
    """Return the first provider whose API key is set in the environment.

    Priority: ANTHROPIC → OPENAI → OPENROUTER → GEMINI → MISTRAL → ollama → mock
    """
    for env_var, name, model in _ENV_MAP:
        key = os.environ.get(env_var, "").strip()
        if key:
            return DetectedProvider(name=name, api_key=key, model=model, source=env_var)

    # Ollama running locally
    try:
        import urllib.request

        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return DetectedProvider(name="ollama", api_key="", model="llama3", source="ollama_local")
    except Exception:
        pass

    return DetectedProvider(name="mock", api_key="", model="mock", source="fallback")


def detect_provider_config() -> dict[str, str]:
    """Return a minimal provider config dict suitable for patching opencontext.yaml."""
    p = detect_provider()
    cfg: dict[str, str] = {"provider": p.name, "model": p.model}
    if p.api_key:
        cfg["api_key_env"] = _key_for_provider(p.name)
    return cfg


def _key_for_provider(name: str) -> str:
    for env_var, pname, _ in _ENV_MAP:
        if pname == name:
            return env_var
    return ""
