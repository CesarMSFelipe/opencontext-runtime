"""OpenContext Runtime core package."""

from opencontext_core.config import (
    ArtifactStoreConfig,
    ArtifactStoreMode,
    ChainStrategy,
    DeliveryStrategy,
    KnowledgeGraphConfig,
    OpenContextConfig,
    SDDConfig,
    SkillsConfig,
    StorageConfig,
    load_config,
)
from opencontext_core.doctor.deep import (
    DeepDiagnostic,
    DeepReport,
    run_deep_diagnostics,
)
from opencontext_core.evaluation.benchmark_suite import (
    ContextScore,
    ContextScorer,
    QualityDimension,
)
from opencontext_core.paths import StorageMode
from opencontext_core.plugin_system import (
    InstallResult,
    Plugin,
    PluginInfo,
    PluginInstaller,
    PluginRegistry,
    PluginUpdater,
    RegistryFetcher,
    RegistryPlugin,
    RegistryVersion,
)
from opencontext_core.runtime import (
    OpenContextRuntime,
    PreparedContext,
    ProjectSetupResult,
    RuntimeResult,
)
from opencontext_core.setup.plan import (
    FileChange,
    InstallAction,
    InstallPlan,
    build_plan,
)
from opencontext_core.setup.presets import (
    COMPONENT_CATALOG,
    PRESET_CATALOG,
    PROFILE_CATALOG,
    ComponentDef,
    PresetDef,
    ProfileDef,
    get_available_components,
    get_available_presets,
    get_available_profiles,
    resolve_preset_components,
)
from opencontext_core.state import (
    ComponentState,
    InstallationState,
    StateStore,
)
from opencontext_core.update import (
    UpdateCheck,
    UpdateChecker,
)
from opencontext_core.user_prefs import (
    UserConfigStore,
    UserFeatures,
    UserPreferences,
)
from opencontext_core.verification import (
    CheckResult,
    VerificationReport,
    run_all_checks,
)
from opencontext_core.wizard import (
    reconfigure,
    reset_config,
    run_wizard,
    show_config,
)

__all__ = [
    "COMPONENT_CATALOG",
    "PRESET_CATALOG",
    "PROFILE_CATALOG",
    "ArtifactStoreConfig",
    "ArtifactStoreMode",
    # Benchmark
    "ChainStrategy",
    "CheckResult",
    "ComponentDef",
    "ComponentState",
    "ContextScore",
    "ContextScorer",
    "DeepDiagnostic",
    "DeepReport",
    "DeliveryStrategy",
    "FileChange",
    "InstallAction",
    "InstallPlan",
    "InstallResult",
    "InstallationState",
    "KnowledgeGraphConfig",
    "OpenContextConfig",
    "OpenContextRuntime",
    "Plugin",
    "PluginInfo",
    "PluginInstaller",
    "PluginRegistry",
    "PluginUpdater",
    "PreparedContext",
    "PresetDef",
    "ProfileDef",
    "ProjectSetupResult",
    "QualityDimension",
    "RegistryFetcher",
    "RegistryPlugin",
    "RegistryVersion",
    "RuntimeResult",
    "SDDConfig",
    "SkillsConfig",
    "StorageConfig",
    "StorageMode",
    "StateStore",
    "UpdateCheck",
    "UpdateChecker",
    "UserConfigStore",
    "UserFeatures",
    "UserPreferences",
    "VerificationReport",
    "build_plan",
    "get_available_components",
    "get_available_presets",
    "get_available_profiles",
    "load_config",
    "reconfigure",
    "reset_config",
    "resolve_preset_components",
    "run_all_checks",
    "run_deep_diagnostics",
    "run_wizard",
    "show_config",
]
