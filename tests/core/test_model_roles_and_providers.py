from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.models.context import DataClassification
from opencontext_core.plugins.manifest import PluginManifest


def test_default_model_roles_present() -> None:
    config = OpenContextConfig.model_validate(default_config_data())
    assert "generate" in config.models.roles
    assert config.models.roles["generate"].provider == "mock"


def test_plugin_manifest_extended_fields() -> None:
    plugin = PluginManifest(name="demo", version="1.0.0", entrypoint="plugins.demo:main")
    assert plugin.type == "analyzer"
    assert plugin.max_data_classification is DataClassification.INTERNAL
