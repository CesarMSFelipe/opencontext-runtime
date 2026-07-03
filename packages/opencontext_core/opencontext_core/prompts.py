"""Keyboard-navigable interactive prompts with a graceful fallback.

Single source of truth for every interactive CLI/wizard prompt so the whole
product has one arrow-key UX and one degradation path. Selectors are driven by
InquirerPy (arrow keys, space to toggle, Enter to confirm). No numbered menus,
no ``(y/n)`` typing.

Degradation, in order:
1. InquirerPy + a real TTY  -> arrow-key selectors / checkboxes.
2. A TTY but no InquirerPy   -> Rich text prompts (still usable).
3. No TTY (CI, pipes, ``--yes`` paths) -> return the default without prompting,
   so automated runs never hang or crash.

Choices accept any of: ``"value"``, ``("value", "label")``, or
``{"value": ..., "name": ...}``. A choice whose value is ``None`` renders as a
non-selectable separator (skipped in the fallbacks).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "SEPARATOR",
    "checkbox",
    "confirm",
    "int_input",
    "pause",
    "secret",
    "select",
    "text",
]

# Sentinel value marking a non-selectable separator row.
SEPARATOR = None

_SELECT_HINT = "↑↓ move · Enter confirm"
_CHECKBOX_HINT = "↑↓ move · Space toggle · Enter confirm"


def _is_tty() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)()) and bool(
        getattr(sys.stdout, "isatty", lambda: False)()
    )


def _inquirer() -> Any | None:
    try:
        from InquirerPy import inquirer
    except ImportError:
        return None
    return inquirer


def _normalize(choices: Sequence[Any]) -> list[tuple[Any, str]]:
    """Return [(value, label), ...]; value is None for separators."""
    out: list[tuple[Any, str]] = []
    for c in choices:
        if c is SEPARATOR:
            out.append((None, ""))
        elif isinstance(c, Mapping):
            out.append((c.get("value"), str(c.get("name", c.get("value", "")))))
        elif isinstance(c, tuple):
            value, label = c
            out.append((value, str(label)))
        else:
            out.append((c, str(c)))
    return out


def _selectable(pairs: list[tuple[Any, str]]) -> list[tuple[Any, str]]:
    return [(v, label) for v, label in pairs if v is not None]


def select(
    message: str,
    choices: Sequence[Any],
    *,
    default: Any = None,
    instruction: str | None = None,
) -> Any:
    """Single-choice selector. Returns the chosen value."""
    pairs = _normalize(choices)
    selectable = _selectable(pairs)
    if not selectable:
        raise ValueError("select() needs at least one selectable choice")
    if default is None:
        default = selectable[0][0]

    iq = _inquirer()
    if iq is not None and _is_tty():
        try:
            from InquirerPy.base.control import Choice
            from InquirerPy.separator import Separator

            iq_choices: list[Any] = [
                Separator(label) if value is None else Choice(value=value, name=label)
                for value, label in pairs
            ]
            return iq.select(
                message=message,
                choices=iq_choices,
                default=default,
                long_instruction=instruction or _SELECT_HINT,
                show_cursor=True,
            ).execute()
        except Exception:
            pass

    if not _is_tty():
        return default

    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    for value, label in pairs:
        console.print(f"  [cyan]{label}[/]" if value is not None else f"[dim]{label}[/]")
    values = [str(v) for v, _ in selectable]
    chosen = Prompt.ask(message, choices=values, default=str(default))
    for value, _ in selectable:
        if str(value) == chosen:
            return value
    return chosen


def checkbox(
    message: str,
    choices: Sequence[Any],
    *,
    defaults: Sequence[Any] = (),
    require_one: bool = False,
    instruction: str | None = None,
) -> list[Any]:
    """Multi-choice selector. Returns the list of chosen values."""
    pairs = _normalize(choices)
    selectable = _selectable(pairs)
    default_set = set(defaults)

    iq = _inquirer()
    if iq is not None and _is_tty():
        try:
            from InquirerPy.base.control import Choice
            from InquirerPy.separator import Separator

            iq_choices: list[Any] = [
                Separator(label)
                if value is None
                else Choice(value=value, name=label, enabled=value in default_set)
                for value, label in pairs
            ]
            kwargs: dict[str, Any] = {
                "message": message,
                "choices": iq_choices,
                "long_instruction": instruction or _CHECKBOX_HINT,
            }
            if require_one:
                kwargs["validate"] = lambda result: len(result) > 0
                kwargs["invalid_message"] = "Select at least one option."
            return list(iq.checkbox(**kwargs).execute())
        except Exception:
            pass

    if not _is_tty():
        return list(defaults)

    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    console.print("  " + ", ".join(f"[cyan]{label}[/]" for value, label in selectable))
    raw = Prompt.ask(
        f"{message} (comma-separated)",
        default=",".join(str(v) for v in defaults),
    )
    picked = [item.strip() for item in raw.split(",") if item.strip()]
    valid = {str(v): v for v, _ in selectable}
    result = [valid[p] for p in picked if p in valid]
    if require_one and not result and selectable:
        return [selectable[0][0]]
    return result


def confirm(message: str, *, default: bool = True) -> bool:
    """Yes/No selector — navigable, never a typed ``(y/n)``."""
    chosen = select(
        message,
        [("yes", "Yes"), ("no", "No")],
        default="yes" if default else "no",
    )
    return bool(chosen == "yes")


def text(message: str, *, default: str = "", instruction: str | None = None) -> str:
    """Free-text input."""
    iq = _inquirer()
    if iq is not None and _is_tty():
        try:
            kwargs: dict[str, Any] = {"message": message, "default": default}
            if instruction:
                kwargs["long_instruction"] = instruction
            return str(iq.text(**kwargs).execute())
        except Exception:
            pass
    if not _is_tty():
        return default
    from rich.prompt import Prompt

    return Prompt.ask(message, default=default)


def int_input(
    message: str,
    *,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
    instruction: str | None = None,
) -> int:
    """Integer input with range clamping and the standard degradation path.

    Values outside ``[min_value, max_value]`` are clamped to the nearest bound
    instead of raising, so a mistyped number never aborts a wizard run.
    """

    def _clamp(value: int) -> int:
        if min_value is not None and value < min_value:
            return min_value
        if max_value is not None and value > max_value:
            return max_value
        return value

    iq = _inquirer()
    if iq is not None and _is_tty():
        try:
            kwargs: dict[str, Any] = {"message": message, "default": default}
            if min_value is not None:
                kwargs["min_allowed"] = min_value
            if max_value is not None:
                kwargs["max_allowed"] = max_value
            if instruction:
                kwargs["long_instruction"] = instruction
            return _clamp(int(iq.number(**kwargs).execute()))
        except Exception:
            pass
    if not _is_tty():
        return _clamp(int(default))
    from rich.prompt import IntPrompt

    return _clamp(int(IntPrompt.ask(message, default=default)))


def secret(message: str) -> str:
    """Hidden input (passwords / API keys)."""
    iq = _inquirer()
    if iq is not None and _is_tty():
        try:
            return str(iq.secret(message=message).execute())
        except Exception:
            pass
    if not _is_tty():
        return ""
    from rich.prompt import Prompt

    return Prompt.ask(message, password=True)


def pause(message: str = "Press Enter to continue") -> None:
    """Wait for Enter; no-op when not interactive."""
    if not _is_tty():
        return
    try:
        input(f"{message}... ")
    except (EOFError, KeyboardInterrupt):
        pass
