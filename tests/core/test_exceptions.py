"""Tests for opencontext_core.exceptions."""


from opencontext_core.exceptions import BackendNotConfiguredError, BackendUnavailableError


def test_backend_unavailable_instantiates():
    err = BackendUnavailableError("semantic-search", "Enable semantic_search in config.")
    assert isinstance(err, Exception)


def test_backend_unavailable_message_format():
    err = BackendUnavailableError("semantic-search", "Enable semantic_search in config.")
    msg = str(err)
    assert "semantic-search" in msg
    assert "not available" in msg


def test_backend_unavailable_feature_attribute():
    err = BackendUnavailableError("persistent-memory", "Configure memory backend.")
    assert err.feature == "persistent-memory"
    assert "Configure memory backend" in err.setup_hint


def test_backend_not_configured_instantiates_and_has_feature():
    err = BackendNotConfiguredError("deep-compression", "OPENCONTEXT_COMPRESSION_KEY")
    assert err.feature == "deep-compression"
    assert err.missing_key == "OPENCONTEXT_COMPRESSION_KEY"
    assert "deep-compression" in str(err)
