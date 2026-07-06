"""Patch executor (EXE-004): a unified-diff file drives the real mutation path.

``opencontext.yaml`` opting in with ``provider: patch`` + ``patch_file:
<root-relative .patch/.diff>`` builds a :class:`PatchGateway`-backed
:class:`~opencontext_core.oc_flow.nodes.ProviderBackedNodeExecutor`. The
gateway converts the unified diff into a schema-valid ``ApplyEdit`` JSON array
(pure Python, no subprocess — the executor honestly declares
``can_run_commands=False``), so the FULL production pipeline runs: parse →
schema-validate → policy → checkpoint → apply → receipt → inspection → verify.

Safety: every path named by the diff must stay inside the workspace. An
absolute path, a ``..`` segment, or a resolved escape raises :class:`PatchError`
and the run is blocked with zero writes. Like ``test_stub``, the resolver keys
are raw-read (never part of the typed production config schema), so ``patch``
can never become a production resolver fallback.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencontext_core.models.llm import LLMRequest, LLMResponse


class PatchError(ValueError):
    """A unified diff that is malformed, unsafe, or does not apply."""


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[tuple[str, str], ...]  # (tag, text) with tag in {" ", "-", "+"}
    no_newline_at_end: bool = False


@dataclass(frozen=True)
class _FilePatch:
    old_path: str | None  # None => file creation (--- /dev/null)
    new_path: str | None  # None => file deletion (+++ /dev/null)
    hunks: tuple[_Hunk, ...]


def _header_path(raw: str) -> str | None:
    """Normalize a ---/+++ header path: drop timestamps, a/ b/ prefixes, /dev/null."""
    token = raw.split("\t", 1)[0].strip()
    if token == "/dev/null":
        return None
    for prefix in ("a/", "b/"):
        if token.startswith(prefix):
            return token[len(prefix) :]
    return token


def parse_patch(text: str) -> list[_FilePatch]:
    """Parse a unified diff into per-file patches; malformed input raises."""
    lines = text.splitlines()
    patches: list[_FilePatch] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("--- "):
            i += 1
            continue
        old_path = _header_path(lines[i][4:])
        i += 1
        if i >= len(lines) or not lines[i].startswith("+++ "):
            raise PatchError("malformed patch: '---' header without a '+++' header")
        new_path = _header_path(lines[i][4:])
        i += 1
        hunks: list[_Hunk] = []
        while i < len(lines) and lines[i].startswith("@@"):
            match = _HUNK_RE.match(lines[i])
            if match is None:
                raise PatchError(f"malformed hunk header: {lines[i]!r}")
            old_start = int(match[1])
            old_count = int(match[2]) if match[2] is not None else 1
            new_start = int(match[3])
            new_count = int(match[4]) if match[4] is not None else 1
            i += 1
            body: list[tuple[str, str]] = []
            no_newline = False
            consumed_old = consumed_new = 0
            while i < len(lines) and (consumed_old < old_count or consumed_new < new_count):
                raw = lines[i]
                if raw.startswith("\\"):
                    # "\ No newline at end of file"
                    no_newline = True
                    i += 1
                    continue
                tag, content = (raw[:1] or " "), raw[1:]
                if tag == " ":
                    consumed_old += 1
                    consumed_new += 1
                elif tag == "-":
                    consumed_old += 1
                elif tag == "+":
                    consumed_new += 1
                else:
                    raise PatchError(f"malformed hunk line: {raw!r}")
                body.append((tag, content))
                i += 1
            if i < len(lines) and lines[i].startswith("\\"):
                no_newline = True
                i += 1
            hunks.append(_Hunk(old_start, old_count, new_start, new_count, tuple(body), no_newline))
        if not hunks:
            raise PatchError("patch declares a file but contains no hunks")
        patches.append(_FilePatch(old_path, new_path, tuple(hunks)))
    if not patches:
        raise PatchError("no file patches found in diff")
    return patches


def _safe_relpath(candidate: str, root: Path) -> str:
    """Return ``candidate`` iff it stays inside ``root``; raise PatchError otherwise."""
    path = Path(candidate)
    if not candidate or path.is_absolute() or ".." in path.parts:
        raise PatchError(f"patch path escapes workspace: {candidate!r}")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise PatchError(f"patch path escapes workspace: {candidate!r}")
    return candidate


def _new_file_content(hunks: tuple[_Hunk, ...]) -> str:
    added = [text for hunk in hunks for tag, text in hunk.lines if tag == "+"]
    trailing = not hunks[-1].no_newline_at_end
    return "\n".join(added) + ("\n" if trailing and added else "")


def _apply_hunks(original: str, hunks: tuple[_Hunk, ...], rel: str) -> str:
    """Apply hunks to ``original`` with strict context validation."""
    lines = original.splitlines()
    out: list[str] = []
    cursor = 0
    for hunk in hunks:
        # For a pure insertion (old_count == 0) the header names the line AFTER
        # which to insert; otherwise it names the first affected line (1-based).
        anchor = hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1
        if anchor < cursor or anchor > len(lines):
            raise PatchError(f"patch does not apply to {rel}: hunk position out of range")
        out.extend(lines[cursor:anchor])
        cursor = anchor
        for tag, text in hunk.lines:
            if tag == "+":
                out.append(text)
                continue
            if cursor >= len(lines) or lines[cursor] != text:
                raise PatchError(f"patch does not apply to {rel}: context mismatch")
            if tag == " ":
                out.append(text)
            cursor += 1
    out.extend(lines[cursor:])
    trailing = original.endswith("\n") or not original
    last = hunks[-1]
    if last.no_newline_at_end and last.lines and last.lines[-1][0] in ("+", " "):
        trailing = False
    return "\n".join(out) + ("\n" if trailing and out else "")


def patch_to_apply_edits(text: str, root: Path) -> list[dict[str, Any]]:
    """Convert a unified diff into ApplyEdit dicts against the workspace at ``root``.

    Raises :class:`PatchError` for malformed diffs, paths escaping the
    workspace, renames, missing targets, and context mismatches — the caller
    blocks the run instead of applying a partial patch.
    """
    root = Path(root)
    edits: list[dict[str, Any]] = []
    for file_patch in parse_patch(text):
        target = file_patch.new_path if file_patch.new_path is not None else file_patch.old_path
        if target is None:
            raise PatchError("patch names no target path")
        rel = _safe_relpath(target, root)
        reason = f"apply configured patch hunk(s) to {rel}"
        refs = [f"patch applies cleanly to {rel}"]
        if file_patch.old_path is None:
            edits.append(
                {
                    "path": rel,
                    "operation": "create_file",
                    "content": _new_file_content(file_patch.hunks),
                    "reason": reason,
                    "requirement_refs": refs,
                }
            )
            continue
        if file_patch.new_path is None:
            edits.append(
                {
                    "path": rel,
                    "operation": "delete_file",
                    "reason": reason,
                    "requirement_refs": refs,
                }
            )
            continue
        if file_patch.old_path != file_patch.new_path:
            raise PatchError("patch renames are not supported")
        source = root / rel
        if not source.is_file():
            raise PatchError(f"patch target missing: {rel}")
        original = source.read_text(encoding="utf-8")
        edits.append(
            {
                "path": rel,
                "operation": "replace_range",
                "start_line": 1,
                "end_line": max(1, len(original.splitlines())),
                "content": _apply_hunks(original, file_patch.hunks, rel),
                "reason": reason,
                "requirement_refs": refs,
            }
        )
    return edits


class PatchGateway:
    """Deterministic gateway that answers with the diff's ApplyEdit JSON array.

    Mirrors the ``TestStubGateway`` seam so ``ProviderBackedNodeExecutor`` runs
    its normal parse → validate → policy → apply → verify pipeline. A rejected
    patch (escape, mismatch, malformed) yields a non-JSON response, which the
    executor reports as a blocked run — never a partial mutation.
    """

    def __init__(self, patch_file: Path, root: Path) -> None:
        self._patch_text = Path(patch_file).read_text(encoding="utf-8")
        self._root = Path(root)

    def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            content = json.dumps(patch_to_apply_edits(self._patch_text, self._root))
        except PatchError as exc:
            # No brackets: the executor's array-extraction must not find JSON here.
            content = f"patch rejected: {exc}".replace("[", "(").replace("]", ")")
        return LLMResponse(
            content=content,
            provider="patch",
            model="patch",
            input_tokens=0,
            output_tokens=0,
        )


def resolve_patch_executor(root: Path) -> Any:
    """Build the patch executor IFF config explicitly opts in; else ``None``.

    Requires ``provider: patch`` plus a ``patch_file`` that exists under
    ``root``. Any other state returns ``None`` so resolution behaves exactly as
    the pre-change production path (mutation tasks stay ``needs_executor``).
    """
    from opencontext_core.config_resolver import resolve_config_path
    from opencontext_core.oc_flow.cli import _read_yaml_mapping, _within
    from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor

    raw = _read_yaml_mapping(resolve_config_path(root, None))
    if raw.get("provider") != "patch":
        return None
    patch_file = raw.get("patch_file")
    if not patch_file or not isinstance(patch_file, str):
        return None
    root_resolved = Path(root).resolve()
    resolved = (root_resolved / patch_file).resolve()
    if not resolved.is_file() or not _within(root_resolved, resolved):
        return None
    return ProviderBackedNodeExecutor(
        gateway=PatchGateway(resolved, root_resolved), root=root, provider="patch"
    )
