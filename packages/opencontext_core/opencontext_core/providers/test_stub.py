"""Config-driven deterministic provider gateway (TEST-ONLY — never a production fallback).

:class:`TestStubGateway` lets CI drive the REAL ``opencontext run`` mutation path with
zero credentials and zero in-process executor injection. It is constructed by
:func:`opencontext_core.oc_flow.cli._resolve_executor` ONLY when ``opencontext.yaml``
explicitly declares ``provider: test_stub`` together with a resolvable ``edits_file``
(PROD-002 / design B2). It is structurally absent from ``detect_provider`` and the
typed :class:`opencontext_core.config.OpenContextConfig` schema, so it can never be a
production resolver fallback.

The gateway reads a JSON ``edits_file`` — an ApplyEdit array — and returns it verbatim
as the ``content`` of a fixed :class:`LLMResponse`, exactly the shape
``ProviderBackedNodeExecutor.mutate`` consumes via ``_parse_apply_edit_set``. Only the
network round-trip is replaced; every other stage (parse, schema-validate, policy,
checkpoint, apply, receipt, inspection, verify) runs the genuine production code path.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.models.llm import LLMRequest, LLMResponse


class TestStubGateway:
    """Deterministic, credential-free provider gateway backed by a JSON ``edits_file``.

    TEST-ONLY: reachable exclusively from an explicit ``provider: test_stub`` config;
    never from ``detect_provider`` or any production resolver path.
    """

    # Tell pytest this is NOT a test class (the ``Test`` name prefix would otherwise
    # trigger a PytestCollectionWarning when the symbol is imported into a test module).
    __test__ = False

    def __init__(self, edits_file: Path) -> None:
        # Read once at construction so the JSON edit set is fixed for the run.
        self._content = Path(edits_file).read_text(encoding="utf-8")

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Return the ``edits_file`` JSON verbatim as the response content.

        The content is an ApplyEdit array; ``_parse_apply_edit_set`` in
        ``oc_flow/nodes.py`` validates it and the executor applies it for real.
        """
        return LLMResponse(
            content=self._content,
            provider="test_stub",
            model="test-stub",
            input_tokens=0,
            output_tokens=0,
        )
