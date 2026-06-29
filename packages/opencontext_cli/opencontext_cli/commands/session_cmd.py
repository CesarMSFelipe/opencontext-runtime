"""session — operate over runtime sessions (PR-013, SPEC-CLI-013-09).

``opencontext session list|status <id>|resume <id>|archive <id>`` over the
shared :class:`~opencontext_core.runtime.api.RuntimeApi` / ``SessionStore``. The
runtime session tree lives under ``.opencontext/sessions/<id>/``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from opencontext_cli.output import add_output_flag, emit, resolve_output_mode


def _root(args: Any) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


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
                        "active_run_id": getattr(session, "active_run_id", None),
                    }
                )

        def _human(_: dict[str, Any]) -> None:
            if not rows:
                print("No runtime sessions found.")
                return
            for r in rows:
                print(f"{r['session_id']}\t{r['status']}\t{r['task'][:48]}")

        emit({"sessions": rows}, mode, _human)
        return

    api = RuntimeApi(root=root)
    sid = getattr(args, "session_id", "")

    try:
        if command == "status":
            report = api.inspect(sid)
            data = report.model_dump()
        elif command == "resume":
            data = api.resume(sid).model_dump()
        elif command == "archive":
            data = api.archive(sid).model_dump()
        else:
            print("Usage: opencontext session [list|status|resume|archive]", file=sys.stderr)
            sys.exit(2)
    except FileNotFoundError:
        print(f"Session not found: {sid}", file=sys.stderr)
        sys.exit(1)

    def _human(d: dict[str, Any]) -> None:
        for key, value in d.items():
            print(f"{key:<16}: {value}")

    emit(data, mode, _human)
