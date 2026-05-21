"""Tree-sitter grammar management.

Downloads and installs tree-sitter language grammars for
code parsing support.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

# Built-in grammar URLs for common languages
BUILTIN_GRAMMARS: dict[str, str] = {
    "python": "https://github.com/tree-sitter/tree-sitter-python",
    "javascript": "https://github.com/tree-sitter/tree-sitter-javascript",
    "typescript": "https://github.com/tree-sitter/tree-sitter-typescript",
    "tsx": "https://github.com/tree-sitter/tree-sitter-typescript",
    "go": "https://github.com/tree-sitter/tree-sitter-go",
    "rust": "https://github.com/tree-sitter/tree-sitter-rust",
    "java": "https://github.com/tree-sitter/tree-sitter-java",
    "c": "https://github.com/tree-sitter/tree-sitter-c",
    "cpp": "https://github.com/tree-sitter/tree-sitter-cpp",
    "php": "https://github.com/tree-sitter/tree-sitter-php",
    "ruby": "https://github.com/tree-sitter/tree-sitter-ruby",
    "swift": "https://github.com/tree-sitter/tree-sitter-swift",
    "kotlin": "https://github.com/tree-sitter/tree-sitter-kotlin",
    "scala": "https://github.com/tree-sitter/tree-sitter-scala",
    "dart": "https://github.com/tree-sitter/tree-sitter-dart",
}


class TreeSitterGrammarManager:
    """Manages tree-sitter language grammars.

    Downloads grammars from GitHub and compiles them for use
    with the tree-sitter Python bindings.
    """

    GRAMMAR_DIR = ".opencontext/grammars"
    GRAMMAR_MANIFEST = ".opencontext/grammars/manifest.json"

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.grammar_dir = self.project_root / self.GRAMMAR_DIR
        self.grammar_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.project_root / self.GRAMMAR_MANIFEST

    def install_grammar(self, language: str, url: str | None = None) -> dict[str, Any]:
        """Install a grammar for a language.

        Args:
            language: Language identifier (e.g., "python").
            url: Optional grammar repository URL.

        Returns:
            Installation report.
        """

        if url is None:
            url = BUILTIN_GRAMMARS.get(language)
            if url is None:
                return {
                    "status": "error",
                    "message": f"No built-in grammar for {language}. Provide a URL.",
                }

        lang_dir = self.grammar_dir / language

        # Clone or update repository
        if lang_dir.exists():
            # Pull latest
            try:
                subprocess.run(
                    ["git", "pull", "--depth", "1"],
                    cwd=lang_dir,
                    capture_output=True,
                    check=True,
                )
            except (subprocess.SubprocessError, FileNotFoundError):
                pass
        else:
            # Clone repository
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", url, str(lang_dir)],
                    capture_output=True,
                    check=True,
                )
            except (subprocess.SubprocessError, FileNotFoundError) as exc:
                return {
                    "status": "error",
                    "message": f"Failed to clone grammar: {exc}",
                }

        # Update manifest
        manifest = self._load_manifest()
        manifest[language] = {
            "url": url,
            "installed_at": str(Path.cwd()),
            "path": str(lang_dir),
        }
        self._save_manifest(manifest)

        return {
            "status": "installed",
            "language": language,
            "path": str(lang_dir),
        }

    def install_all(self) -> dict[str, Any]:
        """Install all built-in grammars."""

        results = []
        for language in sorted(BUILTIN_GRAMMARS.keys()):
            result = self.install_grammar(language)
            results.append(result)

        installed = sum(1 for r in results if r["status"] == "installed")
        return {
            "status": "completed",
            "installed": installed,
            "total": len(results),
            "results": results,
        }

    def list_installed(self) -> list[dict[str, Any]]:
        """List installed grammars."""

        manifest = self._load_manifest()
        grammars = []
        for language, info in sorted(manifest.items()):
            lang_dir = Path(info["path"])
            grammars.append(
                {
                    "language": language,
                    "url": info.get("url", ""),
                    "path": str(lang_dir),
                    "exists": lang_dir.exists(),
                }
            )
        return grammars

    def is_installed(self, language: str) -> bool:
        """Check if a grammar is installed."""

        manifest = self._load_manifest()
        return language in manifest

    def remove_grammar(self, language: str) -> dict[str, Any]:
        """Remove a grammar."""

        manifest = self._load_manifest()
        if language not in manifest:
            return {"status": "not_found", "language": language}

        info = manifest.pop(language)
        self._save_manifest(manifest)

        lang_dir = Path(info["path"])
        if lang_dir.exists():
            import shutil

            shutil.rmtree(lang_dir)

        return {"status": "removed", "language": language}

    def _load_manifest(self) -> dict[str, Any]:
        """Load grammar manifest."""

        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        """Save grammar manifest."""

        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
