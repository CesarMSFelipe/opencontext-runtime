"""Safely configure existing AI coding agents without clobbering user files."""

from opencontext_core.configurator.filemerge import (
    inject_managed_section,
    merge_mcp_servers,
    write_text_atomic,
)

__all__ = [
    "inject_managed_section",
    "merge_mcp_servers",
    "write_text_atomic",
]
