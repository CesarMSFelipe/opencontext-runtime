"""Checkpoint snapshot / diff / restore around harness writes."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.checkpoint import CheckpointStore


class TestCheckpointSnapshotRestore:
    def test_restore_makes_files_byte_identical(self, tmp_path: Path) -> None:
        a = tmp_path / "a.py"
        b = tmp_path / "sub" / "b.py"
        b.parent.mkdir(parents=True, exist_ok=True)
        a.write_bytes(b"A0\n")
        b.write_bytes(b"B0\n")

        store = CheckpointStore(tmp_path)
        cp = store.create([a, b])
        assert cp is not None

        # Mutate both files after the snapshot.
        a.write_bytes(b"A1-changed\n")
        b.write_bytes(b"B1-changed\n")

        cp.restore()

        assert a.read_bytes() == b"A0\n"
        assert b.read_bytes() == b"B0\n"

    def test_restore_deletes_files_that_did_not_exist(self, tmp_path: Path) -> None:
        created = tmp_path / "created.py"  # absent at snapshot time
        store = CheckpointStore(tmp_path)
        cp = store.create([created])
        assert cp is not None

        created.write_bytes(b"now exists\n")
        cp.restore()

        assert not created.exists()

    def test_empty_paths_returns_none(self, tmp_path: Path) -> None:
        store = CheckpointStore(tmp_path)
        assert store.create([]) is None

    def test_checkpoint_lives_under_harness_owned_location(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_bytes(b"x\n")
        store = CheckpointStore(tmp_path)
        cp = store.create([f])
        assert cp is not None
        assert (tmp_path / ".opencontext" / "checkpoints") in cp.dir.parents


class TestCheckpointDiff:
    def test_diff_reports_modified_created_and_deleted(self, tmp_path: Path) -> None:
        modified = tmp_path / "m.py"
        deleted = tmp_path / "d.py"
        created = tmp_path / "c.py"  # absent at snapshot
        unchanged = tmp_path / "u.py"
        modified.write_bytes(b"m0\n")
        deleted.write_bytes(b"d0\n")
        unchanged.write_bytes(b"u0\n")

        store = CheckpointStore(tmp_path)
        cp = store.create([modified, deleted, created, unchanged])
        assert cp is not None

        modified.write_bytes(b"m1\n")
        deleted.unlink()
        created.write_bytes(b"c1\n")

        diff = {c.path: c.change for c in cp.diff()}
        assert diff[str(modified)] == "modified"
        assert diff[str(deleted)] == "deleted"
        assert diff[str(created)] == "created"
        assert str(unchanged) not in diff

    def test_diff_empty_when_nothing_changed(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_bytes(b"same\n")
        store = CheckpointStore(tmp_path)
        cp = store.create([f])
        assert cp is not None
        assert cp.diff() == []
