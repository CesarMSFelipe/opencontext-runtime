"""Deep compression backend — opt-in stub requiring optional dependency."""

from __future__ import annotations

from opencontext_core.exceptions import BackendUnavailableError
from opencontext_core.models.context import ProtectedSpan


class DeepCompressionBackend:
    """
    Deep token-level compression. Requires optional dependency.
    Raises BackendUnavailableError — never mentions underlying technology.
    """

    name = "deep"

    def __init__(self) -> None:
        try:
            import llmlingua as _  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as exc:
            raise BackendUnavailableError(
                "deep-compression",
                "opencontext setup --enable deep-compression",
            ) from exc

    def compress(self, text: str, protected_spans: list[ProtectedSpan]) -> str:
        return text  # pragma: no cover
