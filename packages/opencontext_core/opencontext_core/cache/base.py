"""Cache interfaces and deterministic key generation.

Also hosts the PR-000.3 unified, typed cache entry layer (``CacheEntry`` base,
``CacheType``, ``CacheProvenance``, ``CacheStore`` Protocol, ``CacheStats``).
The cache is an L4 *leaf* utility (book doc 58): it takes keys + producers and
returns values; it must never import KG / Memory / Context / Provider.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Internal contract version (doc 59 §Internal contract versioning — "Cache
# Contract v1"). Bump on a breaking change; a guard test asserts this value so
# accidental drift is caught.
CACHE_CONTRACT_VERSION = 1


class CacheKey(BaseModel):
    """Deterministic cache key fields for prompt and response caches."""

    model_config = ConfigDict(extra="forbid")

    workflow_name: str = Field(description="Workflow name.")
    tenant_id: str = Field(default="default", description="Tenant scope.")
    project_id: str = Field(default="default", description="Project scope identifier.")
    project_hash: str = Field(description="Project manifest or project state hash.")
    provider: str = Field(default="mock", description="Provider identifier.")
    model_name: str = Field(description="Model name.")
    prompt_version: str = Field(description="Prompt assembly version.")
    classifications: tuple[str, ...] = Field(
        default=("internal",),
        description="Classifications represented in cached context.",
    )
    normalized_input_hash: str = Field(description="Hash of normalized user input.")
    context_hash: str = Field(description="Hash of selected context.")

    @property
    def value(self) -> str:
        """Return a stable key string."""

        payload = self.model_dump()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ResponseCache(Protocol):
    """Interface for exact response caches."""

    def get(self, key: CacheKey) -> str | None:
        """Return cached response content if present."""

    def set(self, key: CacheKey, value: str) -> None:
        """Store response content."""


class SemanticCache(Protocol):
    """Conservative semantic cache boundary, disabled by default."""

    def lookup(self, key: CacheKey, text: str) -> str | None:
        """Return a semantically similar cached response if safely reusable."""


def build_cache_key(
    *,
    workflow_name: str,
    tenant_id: str = "default",
    project_id: str = "default",
    project_hash: str,
    provider: str = "mock",
    model_name: str,
    prompt_version: str,
    user_input: str,
    context: str,
    classifications: tuple[str, ...] = ("internal",),
) -> CacheKey:
    """Build a deterministic cache key from runtime identity fields."""

    return CacheKey(
        workflow_name=workflow_name,
        tenant_id=tenant_id,
        project_id=project_id,
        project_hash=project_hash,
        provider=provider,
        model_name=model_name,
        prompt_version=prompt_version,
        classifications=tuple(sorted(set(classifications))),
        normalized_input_hash=_hash_text(_normalize(user_input)),
        context_hash=_hash_text(context),
    )


def cache_allowed_for_classifications(classifications: tuple[str, ...]) -> bool:
    """Fail closed for high-risk classifications by default."""

    blocked = {"secret", "regulated"}
    return not any(item in blocked for item in classifications)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# PR-000.3 — unified typed cache entry layer                                   #
# --------------------------------------------------------------------------- #


class CacheType(StrEnum):
    """The seven cache types unified by the PR-000.3 cache layer (book §5)."""

    semantic = "semantic"
    prompt_context = "prompt_context"
    tool_output = "tool_output"
    ast = "ast"
    provider_response = "provider_response"
    kg_query = "kg_query"
    memory_retrieval = "memory_retrieval"


def cache_entry_id(key_value: str) -> str:
    """Return a content-addressed cache id (doc 59 — ``cache_<hash>``)."""

    digest = hashlib.sha256(key_value.encode("utf-8")).hexdigest()[:24]
    return f"cache_{digest}"


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class CacheProvenance(BaseModel):
    """Provenance fingerprints making a cached value reconstructable/auditable.

    ``source_files`` maps a (relative) source path to its content hash; the
    invalidator (``cache/invalidation.py``) drops an entry when any referenced
    path changes.
    """

    model_config = ConfigDict(extra="forbid")

    produced_by_run: str | None = Field(default=None, description="Run id that produced the value.")
    source_refs: list[str] = Field(
        default_factory=list, description="Logical source ids (tool/query/memory ids)."
    )
    source_files: dict[str, str] = Field(
        default_factory=dict, description="Source path -> content hash fingerprints."
    )
    content_hash: str = Field(default="", description="Content hash of the cached body.")


class CacheEntry(BaseModel):
    """Shared base for every typed cache entry (doc 59 — Cache Contract v1).

    The bespoke entry layer is reserved for what stdlib ``functools.lru_cache`` /
    ``@cache`` cannot do: cross-run persistence, file-change invalidation,
    per-entry provenance, classification/redaction governance, and hit/miss
    telemetry. In-process pure memoization stays on stdlib.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.cache_entry.v1"
    contract_version: int = CACHE_CONTRACT_VERSION
    entry_id: str = Field(default="", description="Content-addressed cache id (cache_<hash>).")
    key: str = Field(default="", description="Deterministic CacheKey hash.")
    cache_type: CacheType
    value_ref: str = Field(default="", description="Content-addressed body ref (sha256).")
    provenance: CacheProvenance = Field(default_factory=CacheProvenance)
    classification: str = Field(default="internal", description="Eligibility classification.")
    created_at: str = Field(default_factory=_now_iso)
    expires_at: str | None = None
    hits: int = 0
    misses: int = 0

    @model_validator(mode="after")
    def _fill_entry_id(self) -> CacheEntry:
        if not self.entry_id and self.key:
            self.entry_id = cache_entry_id(self.key)
        return self


class CacheStats(BaseModel):
    """Aggregate hit/miss telemetry — the stable surface PR-011 consumes."""

    model_config = ConfigDict(extra="forbid")

    entries: int = 0
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    by_type: dict[str, dict[str, int]] = Field(default_factory=dict)


class CacheStore(Protocol):
    """Cache API Protocol (doc 59 — ``get`` / ``put`` / ``invalidate``).

    Upper layers depend on this Protocol, never the concrete store, so the
    compatibility layer can swap implementations without touching callers.
    """

    def get(self, key: str) -> CacheEntry | None:
        """Return the cached entry for ``key`` (a hit) or ``None`` (a miss)."""

    def put(self, entry: CacheEntry, body: str) -> None:
        """Store ``entry`` + ``body``, gated by classification + redaction."""

    def invalidate_paths(self, paths: list[str], *, cache_types: list[str] | None = None) -> int:
        """Drop entries whose provenance references any of ``paths``; return count.

        ``cache_types`` (optional) narrows invalidation to those cache types.
        """

    def stats(self) -> CacheStats:
        """Return aggregate hit/miss telemetry."""
