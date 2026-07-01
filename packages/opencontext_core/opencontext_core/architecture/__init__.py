"""Architecture coverage — release-gate contract for the v2 capability set.

This package is the single source of truth for the architecture coverage
report that ships in the 1.0 release evidence. It exposes two related
surfaces:

* the **AST guard** — :func:`walk_v2_modules` / :func:`iter_v2_modules`
  walk ``packages/opencontext_core/opencontext_core/<x>/v2/`` and assert
  every discovered subpackage's ``__init__.py`` carries a string
  ``__capability__`` annotation.
* the **traceability matrix** — :func:`build_traceability_matrix` /
  :func:`coverage_report` produce the audit artifact (schema
  ``opencontext.architecture_coverage.v1``) reviewers can scan.

The eight v2 capability ids the report tracks are the ones enumerated
in :data:`opencontext_core.capabilities.registry.REGISTERED_V2_CAPABILITIES`.
Other v2 subpackages that exist in the tree (e.g. ``benchmarks/v2``)
are tracked separately by their own gate machinery and are excluded
from this walker.
"""
