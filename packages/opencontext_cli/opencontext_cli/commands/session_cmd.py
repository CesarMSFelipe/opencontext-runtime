"""session — operate over runtime sessions (PR-013, SPEC-CLI-013-09).

``opencontext session list|status <id>|resume <id>|archive <id>`` over the
shared :class:`~opencontext_core.runtime.api.RuntimeApi` / ``SessionStore``. The
runtime session tree lives under ``.opencontext/sessions/<id>/``.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencontext_cli.output import add_output_flag, emit, eprint, resolve_output_mode
from opencontext_core.dx.console_styles import console


def _root(args: Any) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _iso_mtime(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _oc_flow_session_row(session_dir: Path) -> dict[str, Any] | None:
    """Derive a session row from the oc_flow on-disk layout (PR-002).

    Reads ``<session_dir>/session.json`` or ``state.json`` when present, then
    falls back to the most-recent ``runs/<run_id>/state.json`` written by
    ``opencontext run`` (oc_flow). Returns ``None`` when nothing readable.
    """
    session_id = session_dir.name

    # Session-level record, if oc_flow/PR-002 wrote one.
    for name in ("session.json", "state.json"):
        rec = _read_json(session_dir / name)
        if rec:
            return {
                "session_id": rec.get("session_id", session_id),
                "status": str(rec.get("status", "")),
                "task": str(rec.get("task", "")),
                "workflow": str(rec.get("workflow", "")),
                "active_run_id": rec.get("active_run_id") or rec.get("run_id"),
                "created": rec.get("created") or rec.get("created_at") or _iso_mtime(session_dir),
            }

    # Fall back to the latest run-level state.json under runs/<run_id>/.
    runs_dir = session_dir / "runs"
    if not runs_dir.is_dir():
        return None
    run_states = [
        run_dir / "state.json"
        for run_dir in runs_dir.iterdir()
        if run_dir.is_dir() and (run_dir / "state.json").is_file()
    ]
    if not run_states:
        return None
    latest = max(run_states, key=lambda p: p.stat().st_mtime)
    rec = _read_json(latest) or {}
    return {
        "session_id": rec.get("session_id", session_id),
        "status": str(rec.get("status", "")),
        "task": str(rec.get("task", "")),
        "workflow": str(rec.get("workflow", "")),
        "active_run_id": rec.get("run_id"),
        "created": _iso_mtime(latest),
    }


def _oc_flow_sessions(root: Path) -> list[dict[str, Any]]:
    """List sessions from the ``.opencontext/sessions/`` tree ``run`` writes."""
    sessions_path = root / ".opencontext" / "sessions"
    rows: list[dict[str, Any]] = []
    if not sessions_path.is_dir():
        return rows
    for session_dir in sorted(sessions_path.glob("*")):
        if not session_dir.is_dir():
            continue
        row = _oc_flow_session_row(session_dir)
        if row is not None:
            rows.append(row)
    return rows


def add_session_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "session",
        help="Operate over runtime sessions (list/status/resume/archive).",
    )
    sub = parser.add_subparsers(dest="session_command", required=True)

    list_p = sub.add_parser("list", help="List runtime sessions.")
    list_p.add_argument("--root", default=".", help="Project root.")
    list_p.add_argument("--json", action="store_true", help="JSON output.")
    add_output_flag(list_p)

    for verb, helptext in (
        ("status", "Show a session's status."),
        ("resume", "Resume a paused session from its last checkpoint."),
        ("archive", "Archive a session (terminal)."),
    ):
        p = sub.add_parser(verb, help=helptext)
        p.add_argument("session_id", help="Session ID.")
        p.add_argument("--root", default=".", help="Project root.")
        p.add_argument("--json", action="store_true", help="JSON output.")
        add_output_flag(p)

    from opencontext_cli.commands.migration_cmd import add_migrate_subparser

    add_migrate_subparser(sub, "session")


def handle_session(args: Any) -> None:
    from opencontext_core.runtime.api import RuntimeApi
    from opencontext_core.runtime.session_store import SessionStore

    command = getattr(args, "session_command", None)

    if command == "migrate":
        from opencontext_cli.commands.migration_cmd import handle_migrate

        raise SystemExit(handle_migrate("session", args))

    root = _root(args)
    mode = resolve_output_mode(args)

    if command == "list":
        store = SessionStore(root)
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        # Legacy SessionStore source (records with a session.json).
        if store.sessions_path.is_dir():
            for session_dir in sorted(store.sessions_path.glob("*")):
                if not (session_dir / "session.json").is_file():
                    continue
                try:
                    session = store.load_session(session_dir.name)
                except Exception:
                    continue
                rows.append(
                    {
                        "session_id": session.session_id,
                        "status": str(session.status),
                        "task": getattr(session, "task", ""),
                        "workflow": "",
                        "active_run_id": getattr(session, "active_run_id", None),
                        "created": getattr(session, "created_at", ""),
                    }
                )
                seen.add(session.session_id)
        # Union with the oc_flow on-disk session tree (`opencontext run`).
        for row in _oc_flow_sessions(root):
            if row["session_id"] in seen:
                continue
            rows.append(row)
            seen.add(row["session_id"])

        def _human_list(_: dict[str, Any]) -> None:
            console.header("Sessions")
            if not rows:
                console.info("No runtime sessions yet.")
                return
            for r in rows:
                workflow = r.get("workflow") or "-"
                print(f"{r['session_id']}\t{workflow}\t{r['status']}\t{r['task'][:48]}")

        emit({"sessions": rows}, mode, _human_list)
        return

    api = RuntimeApi(root=root)
    sid = getattr(args, "session_id", "")

    try:
        if command == "status":
            try:
                report = api.inspect(sid)
                data = report.model_dump()
            except FileNotFoundError:
                # Fall back to the oc_flow on-disk session tree (`opencontext run`).
                fallback_row = _oc_flow_session_row(root / ".opencontext" / "sessions" / sid)
                if fallback_row is None:
                    raise
                data = fallback_row
        elif command == "resume":
            data = api.resume(sid).model_dump()
        elif command == "archive":
            data = api.archive(sid).model_dump()
        else:
            eprint("Usage: opencontext session [list|status|resume|archive]")
            sys.exit(2)
    except FileNotFoundError:
        eprint(f"Session not found: {sid}")
        sys.exit(1)

    def _human(d: dict[str, Any]) -> None:
        for key, value in d.items():
            print(f"{key:<16}: {value}")

    emit(data, mode, _human)
