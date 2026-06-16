"""Tests for DeepCompressionBackend — must raise BackendUnavailableError."""

import pytest

from opencontext_core.exceptions import BackendUnavailableError


def test_deep_raises_backend_unavailable_error_not_import_error():
    with pytest.raises(BackendUnavailableError):
        from opencontext_core.backends.compression.deep import DeepCompressionBackend

        DeepCompressionBackend()


def test_deep_error_message_contains_feature_name():
    with pytest.raises(BackendUnavailableError) as exc_info:
        from opencontext_core.backends.compression.deep import DeepCompressionBackend

        DeepCompressionBackend()
    assert "deep-compression" in str(exc_info.value)


def test_deep_error_message_contains_setup_hint():
    with pytest.raises(BackendUnavailableError) as exc_info:
        from opencontext_core.backends.compression.deep import DeepCompressionBackend

        DeepCompressionBackend()
    assert "opencontext setup" in str(exc_info.value)


def test_deep_error_message_no_tech_name():
    with pytest.raises(BackendUnavailableError) as exc_info:
        from opencontext_core.backends.compression.deep import DeepCompressionBackend

        DeepCompressionBackend()
    msg = str(exc_info.value).lower()
    assert "llmlingua" not in msg
    assert "pytorch" not in msg
