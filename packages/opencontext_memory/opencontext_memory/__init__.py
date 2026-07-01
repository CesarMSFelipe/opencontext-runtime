"""opencontext_memory - SQLite + FTS5 memory store and MCP-style tools.

Public surface (per ``openspec/changes/agentic-parity-engram-gentle/design.md``
§Public Python API). The package root re-exports every public tool surface
so the host can do a single ``from opencontext_memory import mem_save`` line.

Storage:
* ``MemoryStore`` - SQLite-backed observation store with FTS5 BM25 search and
  ``topic_key`` upsert. Loads the canonical ``store/schema.sql`` on first open.
* ``WriteQueue`` - per-connection lock + cross-process ``fcntl``/``msvcrt``
  advisory lock to serialise concurrent writers in any host.

Project detection:
* ``DetectProjectFull`` - 5-case project detection (REQ-OMPD-001) with
  recovery-token flow.
* ``DetectionResult`` / ``available_projects`` - Pydantic accessor + helper.

Lifecycle:
* ``state`` - pure-function derivation of ``active`` / ``needs_review``.
* ``mark_reviewed`` - resets the decay clock; returns the row + audit.
* ``DECAY_DAYS`` - canonical per-type decay table.

Tools (eager + deferred + admin):
* ``mem_save``, ``mem_search``, ``mem_context``, ``mem_get_observation``,
  ``mem_save_prompt``, ``mem_current_project`` - eager 6.
* ``mem_update``, ``mem_review``, ``mem_suggest_topic_key``, ``mem_capture_passive``,
  ``mem_session_start``, ``mem_session_end``, ``mem_session_summary``,
  ``mem_pin``, ``mem_unpin``, ``mem_judge``, ``mem_compare``, ``mem_delete`` -
  deferred 11.
* ``mem_doctor`` - admin tool aggregating 4 health checks.
"""

from __future__ import annotations

from opencontext_memory.lifecycle import DECAY_DAYS, mark_reviewed, state
from opencontext_memory.models import (
    ConflictEnvelope,
    MemoryRecord,
    MemoryRecordLite,
    RelationRow,
    SaveReceipt,
    SessionRecord,
)
from opencontext_memory.project import DetectionResult, DetectProjectFull, available_projects
from opencontext_memory.store.migrations import MIGRATIONS, migrate
from opencontext_memory.store.sqlite import MemoryStore, Observation, ObservationWriteResult
from opencontext_memory.store.write_queue import WriteQueue
from opencontext_memory.tools.mem_capture_passive import mem_capture_passive
from opencontext_memory.tools.mem_compare import mem_compare
from opencontext_memory.tools.mem_context import mem_context
from opencontext_memory.tools.mem_current_project import mem_current_project
from opencontext_memory.tools.mem_delete import mem_delete

# Tool entry points — expose the function under the canonical name so
# ``from opencontext_memory import mem_save`` works as a callable.
from opencontext_memory.tools.mem_doctor import mem_doctor
from opencontext_memory.tools.mem_get_observation import mem_get_observation
from opencontext_memory.tools.mem_judge import mem_judge
from opencontext_memory.tools.mem_pin import mem_pin
from opencontext_memory.tools.mem_review import mem_review
from opencontext_memory.tools.mem_save import mem_save
from opencontext_memory.tools.mem_save_prompt import mem_save_prompt
from opencontext_memory.tools.mem_search import mem_search
from opencontext_memory.tools.mem_session_end import mem_session_end
from opencontext_memory.tools.mem_session_start import mem_session_start
from opencontext_memory.tools.mem_session_summary import mem_session_summary
from opencontext_memory.tools.mem_suggest_topic_key import mem_suggest_topic_key
from opencontext_memory.tools.mem_unpin import mem_unpin
from opencontext_memory.tools.mem_update import mem_update

__all__ = [
    "DECAY_DAYS",
    "MIGRATIONS",
    "ConflictEnvelope",
    "DetectProjectFull",
    "DetectionResult",
    "MemoryRecord",
    "MemoryRecordLite",
    "MemoryStore",
    "Observation",
    "ObservationWriteResult",
    "RelationRow",
    "SaveReceipt",
    "SessionRecord",
    "WriteQueue",
    "available_projects",
    "mark_reviewed",
    "mem_capture_passive",
    "mem_compare",
    "mem_context",
    "mem_current_project",
    "mem_delete",
    "mem_doctor",
    "mem_get_observation",
    "mem_judge",
    "mem_pin",
    "mem_review",
    "mem_save",
    "mem_save_prompt",
    "mem_search",
    "mem_session_end",
    "mem_session_start",
    "mem_session_summary",
    "mem_suggest_topic_key",
    "mem_unpin",
    "mem_update",
    "migrate",
    "state",
]
