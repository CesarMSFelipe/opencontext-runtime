"""EvolutionStore — file-backed persistence for EvolutionProposals.

Proposals are stored as individual JSON files under
``.opencontext/learning/evolution/<proposal_id>.json``.

This is DISTINCT from ``quality/evolution.py:EvolutionStore``, which tracks
quality *scores*. This store tracks propose-only evolution signals.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path

from opencontext_core.learning.evolution import EvolutionProposal


class EvolutionStore:
    """Persist and retrieve ``EvolutionProposal`` instances.

    Each proposal is stored as a separate JSON file keyed by ``proposal_id``.
    The store directory is created on demand.

    Args:
        root: Project root or an explicit storage directory.  When ``root`` is
            the project root the proposals land in
            ``<root>/.opencontext/learning/evolution/``.
    """

    def __init__(self, root: Path | str = ".") -> None:
        root = Path(root)
        # Detect whether the caller passed the project root or the store dir.
        if root.name == "evolution" and root.parent.name == "learning":
            self._store_dir = root
        else:
            self._store_dir = root / ".opencontext" / "learning" / "evolution"

    def _ensure_dir(self) -> None:
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _proposal_path(self, proposal_id: str) -> Path:
        return self._store_dir / f"{proposal_id}.json"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, proposal: EvolutionProposal) -> Path:
        """Persist a proposal to disk.

        If a proposal with the same ``proposal_id`` already exists it is
        overwritten (idempotent upsert).

        Args:
            proposal: The proposal to persist.

        Returns:
            Path where the proposal was written.
        """
        self._ensure_dir()
        path = self._proposal_path(proposal.proposal_id)
        path.write_text(
            json.dumps(proposal.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        return path

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load(self, proposal_id: str) -> EvolutionProposal | None:
        """Load a single proposal by ID.

        Returns:
            The proposal, or ``None`` if not found.
        """
        path = self._proposal_path(proposal_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return EvolutionProposal.model_validate(data)
        except Exception:
            return None

    def get(self, proposal_id: str) -> EvolutionProposal | None:
        """Alias for ``load()``."""
        return self.load(proposal_id)

    def list(self) -> list[EvolutionProposal]:
        """Return all stored proposals, sorted by proposal_id."""
        if not self._store_dir.exists():
            return []
        proposals: list[EvolutionProposal] = []
        for path in sorted(self._store_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                proposals.append(EvolutionProposal.model_validate(data))
            except Exception:
                continue
        return proposals

    def list_by_status(self, status: str) -> builtins.list[EvolutionProposal]:
        """Return proposals whose ``status`` matches the given value."""
        return [p for p in self.list() if p.status == status]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, proposal_id: str, **kwargs: object) -> EvolutionProposal | None:
        """Update fields on a stored proposal.

        Args:
            proposal_id: ID of the proposal to update.
            **kwargs: Fields to update (e.g. ``status="approved"``).

        Returns:
            The updated proposal, or ``None`` if not found.
        """
        proposal = self.load(proposal_id)
        if proposal is None:
            return None
        updated = proposal.model_copy(update=kwargs)
        self.save(updated)
        return updated

    def update_status(self, proposal_id: str, status: str) -> EvolutionProposal | None:
        """Convenience method to update only the status field."""
        return self.update(proposal_id, status=status)


__all__ = ["EvolutionStore"]
