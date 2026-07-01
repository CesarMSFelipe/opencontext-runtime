"""Local frontmatter-backed context repository."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from opencontext_core.compat import UTC
from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.models.context import ContextPriority, DataClassification
from opencontext_core.paths import StorageMode, resolve_workspace_path
from opencontext_core.safety.redaction import SinkGuard
from opencontext_core.safety.secrets import SecretScanner

REPOSITORY_DIRS = ("system", "memory", "archive", "facts", "decisions", "summaries")
_WORD_RE = re.compile(r"[A-Za-z0-9_./:-]+")
_BACKTICK_RE = re.compile(r"`([^`]{2,120})`")


class MemoryItem(BaseModel):
    """Stored memory item with frontmatter metadata and redacted body."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable memory identifier.")
    kind: str = Field(description="Memory kind such as fact, decision, or summary.")
    classification: DataClassification = Field(description="Security classification.")
    priority: ContextPriority = Field(default=ContextPriority.P2, description="Memory priority.")
    pin: bool = Field(default=False, description="Whether item is always considered.")
    source: str = Field(description="Trace/file/source provenance.")
    valid_from: datetime = Field(description="UTC validity start.")
    valid_until: datetime | None = Field(default=None, description="Optional expiry time.")
    tokens: int = Field(ge=0, description="Token estimate for the redacted body.")
    content: str = Field(description="Redacted memory body.")
    superseded_by: str | None = Field(default=None, description="Replacement memory id.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata.")

    @field_validator("source")
    @classmethod
    def source_required(cls, value: str) -> str:
        """Require provenance for stored memory."""

        if not value.strip():
            raise ValueError("memory source/provenance is required")
        return value


class MemorySearchResult(BaseModel):
    """Traceable memory retrieval result produced by deterministic multi-signal scoring."""

    model_config = ConfigDict(extra="forbid")

    item: MemoryItem = Field(description="Matched memory item.")
    score: float = Field(ge=0.0, description="Fused retrieval score.")
    matched_terms: list[str] = Field(description="Normalized query terms matched in the item.")
    matched_entities: list[str] = Field(description="Entity-like query tokens matched in metadata.")
    reason: str = Field(description="Human-readable match reason.")


class ContextRepository:
    """Stores redacted memory in `.opencontext/context-repository`."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)
        if self.root.name == "context-repository":
            self.base_path = self.root
        else:
            self.base_path = (
                resolve_workspace_path(self.root, StorageMode.local) / "context-repository"
            )

    def init_layout(self) -> list[Path]:
        """Create the repository directory layout."""

        created: list[Path] = []
        for name in REPOSITORY_DIRS:
            path = self.base_path / name
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
        return created

    def store(
        self,
        content: str,
        *,
        kind: str,
        source: str,
        classification: DataClassification = DataClassification.INTERNAL,
        priority: ContextPriority = ContextPriority.P2,
        pin: bool = False,
        collection: str = "memory",
        memory_id: str | None = None,
        valid_until: datetime | None = None,
        entities: set[str] | None = None,
        agent_generated: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        """Store one redacted memory item and return its model."""

        self.init_layout()
        safe_content = SinkGuard().redact(content)[0]
        if SecretScanner().scan(safe_content):
            safe_content = SecretScanner().redact(safe_content)
        # Dedup auto-stores (e.g. harvest summaries) so near-identical records
        # don't accrete every run. Explicit id/pin stores are intentional writes
        # and bypass the gate.
        if memory_id is None and not pin:
            duplicate = self._find_near_duplicate(safe_content, collection)
            if duplicate is not None:
                return duplicate
        extracted_entities = sorted(
            {
                normalized
                for entity in {*_extract_entities(safe_content), *(entities or set())}
                if (normalized := _normalize_entity(entity))
            }
        )
        item_metadata = dict(metadata or {})
        item_metadata.update(
            {
                "agent_generated": agent_generated,
                "entities": extracted_entities,
                "store_raw": False,
            }
        )
        item = MemoryItem(
            id=memory_id or f"mem-{uuid4().hex[:12]}",
            kind=kind,
            classification=classification,
            priority=priority,
            pin=pin,
            source=source,
            valid_from=datetime.now(tz=UTC),
            valid_until=valid_until,
            tokens=estimate_tokens(safe_content),
            content=safe_content,
            metadata=item_metadata,
        )
        self._write_item(item, collection)
        return item

    def _find_near_duplicate(self, content: str, collection: str) -> MemoryItem | None:
        """Return an existing item in ``collection`` that is ~the same as ``content``.

        Jaccard token overlap >= 0.85 counts as a duplicate, so harvest summaries
        that differ only in a run id / timestamp do not pile up.
        """
        new_tokens = set(content.lower().split())
        if not new_tokens:
            return None
        coll_dir = self.base_path / collection
        if not coll_dir.exists():
            return None
        for path in sorted(coll_dir.glob("*.md")):
            try:
                existing = self._read_item(path)
            except Exception:
                continue
            other = set(existing.content.lower().split())
            if not other:
                continue
            union = len(new_tokens | other)
            if union and len(new_tokens & other) / union >= 0.85:
                return existing
        return None

    def list_items(self, *, include_archive: bool = False) -> list[MemoryItem]:
        """List stored memory items."""

        if not self.base_path.exists():
            return []
        collections = (
            REPOSITORY_DIRS
            if include_archive
            else tuple(name for name in REPOSITORY_DIRS if name != "archive")
        )
        items: list[MemoryItem] = []
        for collection in collections:
            for path in sorted((self.base_path / collection).glob("*.md")):
                items.append(self._read_item(path))
        return sorted(items, key=lambda item: (int(item.priority), item.id))

    def get(self, memory_id: str) -> MemoryItem:
        """Load one memory item by id."""

        for item in self.list_items(include_archive=True):
            if item.id == memory_id:
                return item
        raise FileNotFoundError(f"Memory item not found: {memory_id}")

    def search(self, query: str) -> list[MemoryItem]:
        """Search active memory by lowercase term intersection."""

        return [result.item for result in self.search_results(query)]

    def search_results(self, query: str, *, limit: int | None = None) -> list[MemorySearchResult]:
        """Search active memory with keyword, entity, priority, recency, and pin signals."""

        terms = _normalized_terms(query)
        query_entities = {_normalize_entity(entity) for entity in _extract_entities(query)}
        now = datetime.now(tz=UTC)
        results: list[MemorySearchResult] = []
        for item in self.list_items():
            if not _is_active(item, now):
                continue
            result = _score_memory_item(item, terms=terms, query_entities=query_entities, now=now)
            if result is not None:
                results.append(result)
        ordered = sorted(
            results,
            key=lambda result: (-result.score, int(result.item.priority), result.item.id),
        )
        if limit is not None:
            return ordered[:limit]
        return ordered

    def set_pin(self, memory_id: str, pin: bool) -> MemoryItem:
        """Pin or unpin one memory item."""

        path, item = self._find_path(memory_id)
        updated = item.model_copy(update={"pin": pin})
        self._write_item(updated, path.parent.name)
        if path.name != f"{updated.id}.md":
            path.unlink(missing_ok=True)
        return updated

    def move(self, memory_id: str, collection: str) -> MemoryItem:
        """Move an item to another context repository collection."""

        if collection not in REPOSITORY_DIRS:
            raise ValueError(f"Unknown memory collection: {collection}")
        path, item = self._find_path(memory_id)
        self._write_item(item, collection)
        if path.parent.name != collection:
            path.unlink(missing_ok=True)
        return item

    def prune_expired(self) -> list[str]:
        """Move expired or superseded memories to archive."""

        now = datetime.now(tz=UTC)
        moved: list[str] = []
        for item in self.list_items():
            if (item.valid_until is not None and item.valid_until <= now) or item.superseded_by:
                self.move(item.id, "archive")
                moved.append(item.id)
        return moved

    def _find_path(self, memory_id: str) -> tuple[Path, MemoryItem]:
        for collection in REPOSITORY_DIRS:
            path = self.base_path / collection / f"{memory_id}.md"
            if path.exists():
                return path, self._read_item(path)
        raise FileNotFoundError(f"Memory item not found: {memory_id}")

    def _write_item(self, item: MemoryItem, collection: str) -> Path:
        path = self.base_path / collection / f"{item.id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = item.model_dump(mode="json", exclude={"content"})
        rendered = "---\n" + yaml.safe_dump(meta, sort_keys=True) + "---\n\n" + item.content + "\n"
        path.write_text(rendered, encoding="utf-8")
        return path

    def _read_item(self, path: Path) -> MemoryItem:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            raise ValueError(f"Memory item missing frontmatter: {path}")
        _, frontmatter, body = text.split("---", 2)
        metadata = yaml.safe_load(frontmatter) or {}
        if not isinstance(metadata, dict):
            raise ValueError(f"Memory frontmatter must be a mapping: {path}")
        return MemoryItem.model_validate({**metadata, "content": body.strip()})


def _score_memory_item(
    item: MemoryItem,
    *,
    terms: set[str],
    query_entities: set[str],
    now: datetime,
) -> MemorySearchResult | None:
    haystack = f"{item.id} {item.kind} {item.source} {item.content}"
    item_terms = _normalized_terms(haystack)
    matched_terms = sorted(terms.intersection(item_terms))
    item_entities = {
        _normalize_entity(str(entity))
        for entity in item.metadata.get("entities", [])
        if _normalize_entity(str(entity))
    }
    matched_entities = sorted(query_entities.intersection(item_entities))
    has_match = bool(item.pin or matched_terms or matched_entities)
    if not has_match:
        return None

    keyword_score = len(matched_terms) / max(len(terms), 1)
    entity_score = len(matched_entities) / max(len(query_entities), 1)
    priority_score = (5 - min(int(item.priority), 5)) / 5
    age_days = max(0.0, (now - item.valid_from).total_seconds() / 86_400)
    recency_score = max(0.0, 1.0 - (age_days / 90))
    pin_score = 1.0 if item.pin else 0.0
    agent_score = 1.0 if item.metadata.get("agent_generated") else 0.0
    score = (
        keyword_score * 0.42
        + entity_score * 0.25
        + priority_score * 0.13
        + recency_score * 0.10
        + pin_score * 0.06
        + agent_score * 0.04
    )
    reasons = []
    if matched_terms:
        reasons.append("keyword")
    if matched_entities:
        reasons.append("entity")
    if item.pin:
        reasons.append("pin")
    if item.metadata.get("agent_generated"):
        reasons.append("agent_fact")
    return MemorySearchResult(
        item=item,
        score=round(score, 6),
        matched_terms=matched_terms,
        matched_entities=matched_entities,
        reason="+".join(reasons) or "recency",
    )


def _is_active(item: MemoryItem, now: datetime) -> bool:
    if item.valid_until is not None and item.valid_until <= now:
        return False
    return item.superseded_by is None


def _normalized_terms(text: str) -> set[str]:
    return {token.lower() for token in _WORD_RE.findall(text) if len(token) > 1}


def _extract_entities(text: str) -> set[str]:
    entities = set(_BACKTICK_RE.findall(text))
    for token in _WORD_RE.findall(text):
        clean = token.strip(".,;:()[]{}")
        if len(clean) < 3:
            continue
        has_boundary = any(separator in clean for separator in (".", "/", "_", "-"))
        has_mixed_case = any(char.isupper() for char in clean[1:])
        has_acronym = clean.isupper() and len(clean) > 2
        if has_boundary or has_mixed_case or has_acronym:
            entities.add(clean)
    return entities


def _normalize_entity(value: str) -> str:
    return value.strip().strip("`").lower()
