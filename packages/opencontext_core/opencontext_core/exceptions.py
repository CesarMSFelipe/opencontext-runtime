"""Domain exceptions for OpenContext — no external technology names in messages."""

from __future__ import annotations


class BackendUnavailableError(Exception):
    """Raised when an optional OpenContext feature is not available."""

    def __init__(self, feature: str, setup_hint: str) -> None:
        self.feature = feature
        self.setup_hint = setup_hint
        super().__init__(f"OpenContext feature '{feature}' is not available. {setup_hint}")


class BackendNotConfiguredError(Exception):
    """Raised when a required configuration key is missing for a feature."""

    def __init__(self, feature: str, missing_key: str) -> None:
        self.feature = feature
        self.missing_key = missing_key
        super().__init__(
            f"OpenContext feature '{feature}' requires configuration key '{missing_key}'."
        )
