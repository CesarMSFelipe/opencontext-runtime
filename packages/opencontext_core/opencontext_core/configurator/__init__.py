"""Safely configure existing AI coding agents without clobbering user files."""

from opencontext_core.configurator.adapter import (
    KNOWN_AGENTS,
    Adapter,
    get_adapter,
    iter_adapters,
)
from opencontext_core.configurator.backup import (
    BackupRecord,
    BackupStore,
    list_backups,
    restore,
)
from opencontext_core.configurator.filemerge import (
    inject_managed_section,
    merge_mcp_config_file,
    merge_mcp_servers,
    write_text_atomic,
)
from opencontext_core.configurator.mcp_strategy import McpShape, write_mcp_servers
from opencontext_core.configurator.service import Configurator

__all__ = [
    "KNOWN_AGENTS",
    "Adapter",
    "BackupRecord",
    "BackupStore",
    "Configurator",
    "McpShape",
    "get_adapter",
    "inject_managed_section",
    "iter_adapters",
    "list_backups",
    "merge_mcp_config_file",
    "merge_mcp_servers",
    "restore",
    "write_mcp_servers",
    "write_text_atomic",
]
