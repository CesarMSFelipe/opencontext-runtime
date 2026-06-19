"""UI string catalog — English and Spanish."""

from __future__ import annotations

from pathlib import Path

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "install.complete": "Setup complete.",
        "install.no_provider": (
            "No LLM provider detected — context packing, knowledge graph, and MCP tools "
            "work without one. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY "
            "to enable the autonomous loop."
        ),
        "install.provider_detected": "Provider: {name} ({model}) — detected from {source}",
        "install.next_steps_title": "Next Steps",
        "install.step1": "opencontext demo                              # 30-second proof on this repo",  # noqa: E501
        "install.step2": "opencontext pack . --query 'your task' --copy # get verified context",
        "install.step3": "opencontext loop --task 'your task' --flow quick # full agentic run",
        "phase.no_llm": "Phase '{phase}': no model bound — emitted a plan for your agent's model to complete. Run inside your AI agent to use its model, or set a provider for standalone runs.",  # noqa: E501
        "loop.complete": "Loop complete.",
        "loop.aborted": "Aborted by user.",
        "loop.no_index": "No index found. Run 'opencontext index .' first, then retry.",
        "loop.round": "-- Round {n}/{total} --",
        "loop.incomplete": "Loop did not complete after {n} round(s).",
        "memory.gc_dry": "Dry run: {n} item(s) would be pruned.",
        "onboarding.welcome": "Welcome to OpenContext. Let's get you set up.",
        "onboarding.language_prompt": "Preferred language / Idioma preferido [en/es]",
        "onboarding.agent_detected": "Detected: {agents}. Configuring...",
        "onboarding.agent_none": "No supported AI coding tools detected. You can run 'opencontext setup <agent>' later.",  # noqa: E501
        "onboarding.done": "Done! OpenContext is ready.",
    },
    "es": {
        "install.complete": "Configuración completa.",
        "install.no_provider": (
            "Sin proveedor LLM — el packing de contexto, knowledge graph y MCP tools "
            "funcionan sin uno. Configurá ANTHROPIC_API_KEY, OPENAI_API_KEY o "
            "OPENROUTER_API_KEY para habilitar el loop autónomo."
        ),
        "install.provider_detected": "Proveedor: {name} ({model}) — detectado desde {source}",
        "install.next_steps_title": "Próximos pasos",
        "install.step1": "opencontext demo                              # prueba de 30 segundos en este repo",  # noqa: E501
        "install.step2": "opencontext pack . --query 'tu tarea' --copy  # contexto verificado",
        "install.step3": "opencontext loop --task 'tu tarea' --flow quick # ejecución agéntica completa",  # noqa: E501
        "phase.no_llm": "Fase '{phase}': sin modelo asignado — se emitió un plan para que lo complete el modelo de tu agente. Ejecutá OpenContext dentro de tu agente de IA para usar su modelo, o configurá un proveedor para correr en modo standalone.",  # noqa: E501
        "loop.complete": "Loop completo.",
        "loop.aborted": "Abortado por el usuario.",
        "loop.no_index": "No se encontró índice. Ejecutá 'opencontext index .' primero.",
        "loop.round": "-- Ronda {n}/{total} --",
        "loop.incomplete": "El loop no completó después de {n} ronda(s).",
        "memory.gc_dry": "Prueba: {n} elemento(s) se eliminarían.",
        "onboarding.welcome": "Bienvenido a OpenContext. Vamos a configurarlo.",
        "onboarding.language_prompt": "Preferred language / Idioma preferido [en/es]",
        "onboarding.agent_detected": "Detectado: {agents}. Configurando...",
        "onboarding.agent_none": "No se detectaron herramientas de IA compatibles. Podés ejecutar 'opencontext setup <agente>' después.",  # noqa: E501
        "onboarding.done": "¡Listo! OpenContext está configurado.",
    },
}

_current_lang = "en"


def set_language(lang: str) -> None:
    global _current_lang
    _current_lang = lang if lang in _MESSAGES else "en"


def t(key: str, **kwargs: str) -> str:
    """Get translated string. Falls back to English."""
    catalog = _MESSAGES.get(_current_lang, _MESSAGES["en"])
    msg = catalog.get(key, _MESSAGES["en"].get(key, key))
    return msg.format(**kwargs) if kwargs else msg


def load_language_from_config(config_path_or_root: str | Path) -> None:
    """Read ui_language from opencontext.yaml and set it globally."""
    from pathlib import Path

    try:
        import yaml

        root = Path(config_path_or_root)
        yaml_path = root / "opencontext.yaml" if root.is_dir() else root
        if yaml_path.exists():
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            lang = data.get("ui_language", "en")
            set_language(lang)
    except Exception:
        pass
