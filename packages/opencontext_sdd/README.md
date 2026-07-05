# opencontext-sdd

Spec-Driven Development status resolver and dispatcher for OpenContext Runtime.

Provides the canonical `Status` Pydantic model (`schemaName: "opencontext.sdd-status"`) the
host agent reads to drive deterministic next-phase guidance from disk state.

## Public exports

```python
from opencontext_sdd import (
    Status,
    Resolve,
    parse_verify_report,
    RenderDispatcherMarkdown,
    RenderNativePhasePrompt,
)
```
