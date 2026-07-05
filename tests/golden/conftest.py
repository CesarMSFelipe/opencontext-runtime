"""Golden-fixture test data + loader (B4 / B5 / AVH-006).

``tests/golden/<suite>/`` holds the 1.0-minimum golden fixtures: each is a small,
self-contained repo state (``setup`` files), a ``task.txt``, and an ``expected.json``
declaring the expected workflow, artifacts, verification command, result, and the
token/time/mutation ceilings. The five wired suites are:

* ``oc_flow_bugfix_python`` → gate ``oc-flow-localized-bugfix`` (the DoD fixture)
* ``first_run``            → gate ``first-run``
* ``policy_security``      → gate ``policy-security``
* ``resume_rollback``      → gate ``resume-rollback``
* ``provider_fallback``    → gate ``provider-fallback``

Each is provider-free: the bugfix/resume suites drive OC Flow through the Phase-3
injectable ``ProviderBackedNodeExecutor`` with a DETERMINISTIC provider stub (the
fixture's ``provider_stub.json``), so the FULL pipeline runs honestly without a live
LLM. The runners live in :mod:`opencontext_core.evaluation.golden`.

The other five mandatory gates (``sdd-formal-feature``, ``kg-retrieval-precision``,
``memory-usefulness``, ``context-token-efficiency``, ``plugin-compatibility``) stay
framed as ``DeclaredSuite`` and MAY remain ``NOT_MEASURED`` past 1.0-minimum — never a
fake ``MET`` (build-rule #1).

The fixture repos are TEST DATA — intentionally-buggy sources plus their seeded
failing tests. ``collect_ignore_glob`` stops pytest from collecting them in-place;
the :class:`GoldenSuite` runners copy each to a temp dir and exercise it there.
"""

from __future__ import annotations

from pathlib import Path

GOLDEN_ROOT = Path(__file__).resolve().parent

# Do not collect the fixture repos as part of the OpenContext suite — they contain
# deliberately-failing tests and buggy modules that the golden runners fix in temp
# copies. (Patterns are fnmatch-matched against the candidate path.)
collect_ignore_glob = [
    "oc_flow_bugfix_python/*",
    "first_run/*",
    "policy_security/*",
    "resume_rollback/*",
    "provider_fallback/*",
    "kg_call_graph_python/*",
]
