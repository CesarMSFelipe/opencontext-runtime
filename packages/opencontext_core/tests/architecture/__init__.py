"""Architecture coverage — AST guard + traceability matrix for v2 capabilities.

Eight v2 leaf capabilities are registered in the capability registry:

* graph.v2
* context.v2
* memory.v2
* learning.v2
* cache.v2
* plugins.v2
* marketplace.v2
* providers.v2

The coverage walker asserts every discovered v2 subpackage carries a
``__capability__`` annotation in its ``__init__.py`` and that the
registered set matches the discovered set. The traceability matrix is
the audit artifact reviewers scan.
"""
