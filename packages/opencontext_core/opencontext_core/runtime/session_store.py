"""On-disk session store and live-state projection (SPEC RC-006).

Materialises ``.opencontext/sessions/<session_id>/`` containing ``session.json``,
``live-state.json``, ``events.jsonl``, and ``runs/<run_id>/run.json``. All
writes are atomic (tmp + ``replace``). The store never writes
``.opencontext/runs/`` — that namespace stays with the legacy ``RunStore``
(RC-016).
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.runtime.event_bus import JsonlEventBus
from opencontext_core.runtime.run import RuntimeRun
from opencontext_core.runtime.session import LiveState, RuntimeSession


class SessionStore:
    """File-backed store for sessions, runs, events, and live state."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)
        self.sessions_path = self.root / ".opencontext" / "sessions"

    # ----------------------------------------------------------------- paths
    def session_dir(self, session_id: str) -> Path:
        return self.sessions_path / session_id

    def session_json(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.json"

    def events_jsonl(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "events.jsonl"

    def live_state_json(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "live-state.json"

    def runs_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "runs"

    def run_json(self, session_id: str, run_id: str) -> Path:
        return self.runs_dir(session_id) / run_id / "run.json"

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    # -------------------------------------------------------------- sessions
    def create_session(self, session: RuntimeSession) -> RuntimeSession:
        """Materialise the session tree: ``session.json`` + empty ``events.jsonl``
        + initial ``live-state.json``."""
        sid = session.session_id
        # Fill in canonical paths so the persisted record points at its own tree.
        # as_posix: recorded paths stay separator-stable across OSes (Windows opens
        # forward-slash paths fine); the JSON record is portable + assertable.
        session.live_state_path = self.live_state_json(sid).as_posix()
        session.events_path = self.events_jsonl(sid).as_posix()
        session.artifacts_root = self.runs_dir(sid).as_posix()
        self.runs_dir(sid).mkdir(parents=True, exist_ok=True)
        events = self.events_jsonl(sid)
        if not events.exists():
            events.touch()
        self.save_session(session)
        self.write_live_state(
            LiveState(session_id=sid, status=str(session.status), message="session created")
        )
        return session

    def load_session(self, session_id: str) -> RuntimeSession:
        path = self.session_json(session_id)
        if not path.exists():
            raise FileNotFoundError(session_id)
        return RuntimeSession.model_validate_json(path.read_text(encoding="utf-8"))

    def session_exists(self, session_id: str) -> bool:
        return self.session_json(session_id).exists()

    def save_session(self, session: RuntimeSession) -> None:
        session.touch()
        self._atomic_write(self.session_json(session.session_id), session.model_dump_json(indent=2))

    # ------------------------------------------------------------------ runs
    def create_run(self, run: RuntimeRun) -> RuntimeRun:
        self.run_json(run.session_id, run.run_id).parent.mkdir(parents=True, exist_ok=True)
        self.save_run(run)
        return run

    def save_run(self, run: RuntimeRun) -> None:
        self._atomic_write(self.run_json(run.session_id, run.run_id), run.model_dump_json(indent=2))

    def load_run(self, session_id: str, run_id: str) -> RuntimeRun:
        path = self.run_json(session_id, run_id)
        if not path.exists():
            raise FileNotFoundError(run_id)
        return RuntimeRun.model_validate_json(path.read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- events
    def event_bus(self, session_id: str) -> JsonlEventBus:
        return JsonlEventBus(self.events_jsonl(session_id))

    def write_live_state(self, state: LiveState) -> None:
        self._atomic_write(self.live_state_json(state.session_id), state.model_dump_json(indent=2))

    def load_live_state(self, session_id: str) -> LiveState:
        path = self.live_state_json(session_id)
        if not path.exists():
            raise FileNotFoundError(session_id)
        return LiveState.model_validate_json(path.read_text(encoding="utf-8"))
