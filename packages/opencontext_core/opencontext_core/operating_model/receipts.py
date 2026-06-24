"""RunReceiptStore — file-backed store for RunReceipt records."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.operating_model.team import RunReceipt

# NOTE: pruning strategy not yet implemented (Phase 2+)


class RunReceiptStore:
    """Append-only JSONL store for RunReceipt objects."""

    def __init__(self, root: Path | str = ".") -> None:
        self.base_path = Path(root) / ".opencontext" / "receipts"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._store = self.base_path / "receipts.jsonl"

    def save(self, receipt: RunReceipt) -> Path:
        with self._store.open("a", encoding="utf-8") as fh:
            fh.write(receipt.model_dump_json() + "\n")
        return self._store

    def load(self, run_id: str) -> RunReceipt:
        if not self._store.exists():
            raise FileNotFoundError(f"Run receipt not found: {run_id}")
        import json

        with self._store.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("run_id") == run_id:
                    return RunReceipt.model_validate(data)
        raise FileNotFoundError(f"Run receipt not found: {run_id}")

    def list(self) -> list[RunReceipt]:
        if not self._store.exists():
            return []
        receipts: list[RunReceipt] = []
        seen: set[str] = set()
        import json

        with self._store.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    rid = data.get("run_id", "")
                    if rid not in seen:
                        seen.add(rid)
                        receipts.append(RunReceipt.model_validate(data))
                except Exception:
                    continue
        return receipts

    def verify(self, run_id: str) -> dict[str, object]:
        try:
            receipt = self.load(run_id)
        except FileNotFoundError:
            return {"run_id": run_id, "ok": False, "error": "not_found"}
        return {
            "run_id": receipt.run_id,
            "schema_version": receipt.schema_version,
            "ok": True,
            "checks": {
                "policy_hash_present": bool(receipt.policy_hash),
                "context_pack_hash_present": bool(receipt.context_pack_hash),
                "prompt_hash_present": bool(receipt.prompt_hash),
                "trace_id_present": bool(receipt.trace_id),
            },
        }
