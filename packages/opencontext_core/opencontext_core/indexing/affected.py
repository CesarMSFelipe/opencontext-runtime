"""Find test files affected by source changes.

Uses dependency tracing to identify which tests need to run
after code modifications.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from opencontext_core.indexing.graph_db import GraphDatabase


class AffectedTestFinder:
    """Finds test files affected by source file changes.

    Traces import and call dependencies transitively to determine
    which test files should be re-run after changes.
    """

    # Common test file patterns
    TEST_PATTERNS: ClassVar[list[str]] = [
        "test_*.py",
        "*_test.py",
        "*.spec.ts",
        "*.test.ts",
        "*.spec.js",
        "*.test.js",
        "*_test.go",
        "*.test.rs",
        "*Test.java",
        "*Tests.cs",
        "*_spec.rb",
        "test_*",
    ]

    def __init__(
        self,
        db_path: str | Path = ".storage/opencontext/codegraph.db",
    ) -> None:
        self.db = GraphDatabase(db_path=db_path)

    def find_affected(
        self,
        changed_files: list[str],
        root: str | Path = ".",
        max_depth: int = 5,
        filter_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find test files affected by changed source files.

        Args:
            changed_files: List of changed file paths (relative to root).
            root: Project root.
            max_depth: Max dependency traversal depth.
            filter_pattern: Optional glob to filter test files.

        Returns:
            List of affected test file dicts with metadata.
        """

        affected_tests: list[dict[str, Any]] = []
        seen_files: set[str] = set()

        for changed_file in changed_files:
            # Find symbols defined in changed file
            nodes = self.db.get_nodes_by_file(changed_file)

            for node in nodes:
                # Trace transitive callers
                node_id_val: int = node.id  # type: ignore[assignment]
                callers = self._trace_callers(node_id_val, max_depth)

                for caller in callers:
                    caller_file = caller.get("file_path", "")
                    if caller_file in seen_files:
                        continue

                    # Check if this is a test file
                    if self._is_test_file(caller_file):
                        if filter_pattern and not self._match_glob(caller_file, filter_pattern):
                            continue

                        seen_files.add(caller_file)
                        affected_tests.append(
                            {
                                "file": caller_file,
                                "reason": f"tests {node.name}",
                                "changed_file": changed_file,
                                "depth": caller.get("depth", 0),
                            }
                        )

            # Also check import relationships
            imports = self._trace_imports(changed_file, max_depth)
            for imported_file in imports:
                if imported_file in seen_files:
                    continue

                if self._is_test_file(imported_file):
                    if filter_pattern and not self._match_glob(imported_file, filter_pattern):
                        continue

                    seen_files.add(imported_file)
                    affected_tests.append(
                        {
                            "file": imported_file,
                            "reason": f"imports {changed_file}",
                            "changed_file": changed_file,
                            "depth": 0,
                        }
                    )

        # Sort by file path
        affected_tests.sort(key=lambda x: x["file"])
        return affected_tests

    def find_affected_from_git(
        self,
        base_ref: str = "HEAD~1",
        head_ref: str = "HEAD",
        root: str | Path = ".",
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        """Find affected tests from git diff.

        Args:
            base_ref: Base git ref.
            head_ref: Head git ref.
            root: Project root.
            max_depth: Max dependency traversal depth.

        Returns:
            List of affected test files.
        """

        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_ref, head_ref],
                capture_output=True,
                text=True,
                cwd=root,
            )
            changed_files = [f for f in result.stdout.strip().split("\n") if f]
        except (subprocess.SubprocessError, FileNotFoundError):
            changed_files = []

        return self.find_affected(changed_files, root=root, max_depth=max_depth)

    def _trace_callers(
        self,
        node_id: int,
        max_depth: int,
        current_depth: int = 0,
        seen: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Trace callers transitively."""

        if seen is None:
            seen = set()

        if current_depth >= max_depth or node_id in seen:
            return []

        seen.add(node_id)
        results: list[dict[str, Any]] = []

        # Get direct callers
        conn = self.db._connect()
        cursor = conn.execute(
            """
            SELECT n.* FROM nodes n
            JOIN edges e ON n.id = e.source_node_id
            WHERE e.target_node_id = ?
            """,
            (node_id,),
        )

        for row in cursor.fetchall():
            caller_id = row[0]
            caller_file = row[4]
            results.append(
                {
                    "id": caller_id,
                    "name": row[1],
                    "file_path": caller_file,
                    "depth": current_depth,
                }
            )

            # Recurse
            if current_depth + 1 < max_depth:
                results.extend(self._trace_callers(caller_id, max_depth, current_depth + 1, seen))

        return results

    def _trace_imports(
        self,
        file_path: str,
        max_depth: int,
        current_depth: int = 0,
        seen: set[str] | None = None,
    ) -> list[str]:
        """Trace import relationships."""

        if seen is None:
            seen = set()

        if current_depth >= max_depth or file_path in seen:
            return []

        seen.add(file_path)
        results: list[str] = []

        # Find files that import this file
        conn = self.db._connect()
        cursor = conn.execute(
            """
            SELECT DISTINCT n.file_path FROM nodes n
            JOIN edges e ON n.id = e.source_node_id
            WHERE e.kind = 'import' AND e.call_site_file = ?
            """,
            (file_path,),
        )

        for row in cursor.fetchall():
            importer_file = row[0]
            results.append(importer_file)

            if current_depth + 1 < max_depth:
                results.extend(
                    self._trace_imports(importer_file, max_depth, current_depth + 1, seen)
                )

        return results

    @staticmethod
    def _is_test_file(file_path: str) -> bool:
        """Check if file path matches test patterns."""

        import fnmatch

        name = Path(file_path).name
        for pattern in AffectedTestFinder.TEST_PATTERNS:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(file_path, pattern):
                return True
        return False

    @staticmethod
    def _match_glob(file_path: str, pattern: str) -> bool:
        """Match file path against glob pattern."""

        import fnmatch

        return fnmatch.fnmatch(file_path, pattern)

    def close(self) -> None:
        """Close database connection."""

        self.db.close()
