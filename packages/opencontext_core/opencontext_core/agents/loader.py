"""Load and manage agent configurations."""

import json
from pathlib import Path
from typing import Optional

import yaml

from .base import AgentConfig


def load_agent_config(config_path: Path) -> AgentConfig:
    """Load agent configuration from YAML file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        AgentConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Empty configuration: {config_path}")

    return AgentConfig(**data)


def list_available_agents(agents_dir: Path) -> list[tuple[str, Path, AgentConfig]]:
    """List all available agent profiles.

    Args:
        agents_dir: Directory containing agent profiles (.agents/profiles/)

    Returns:
        List of (agent_name, config_path, config) tuples
    """
    profiles_dir = agents_dir / "profiles"
    if not profiles_dir.exists():
        return []

    agents = []
    for config_file in sorted(profiles_dir.glob("*.yaml")):
        try:
            config = load_agent_config(config_file)
            # Use config type as agent identifier if name not suitable
            agent_name = config.type or config_file.stem
            agents.append((agent_name, config_file, config))
        except (ValueError, yaml.YAMLError) as e:
            # Skip invalid configurations but log
            print(f"Warning: Skipping invalid agent config {config_file}: {e}")

    return agents


def validate_config_against_schema(config_data: dict, schema_path: Path) -> bool:
    """Validate configuration against JSON schema.

    Args:
        config_data: Configuration dictionary
        schema_path: Path to JSON schema file

    Returns:
        True if valid, False otherwise

    Note:
        Requires jsonschema library for full validation.
        This is a simplified version that checks required fields.
    """
    required_fields = ["name", "type", "objectives"]
    return all(field in config_data for field in required_fields)


def create_agent_config_file(
    output_path: Path,
    name: str,
    agent_type: str,
    objectives: list[str],
    **kwargs,
) -> None:
    """Create a new agent configuration file.

    Args:
        output_path: Where to save the config file
        name: Agent name
        agent_type: Agent type (code-review, security-audit, etc)
        objectives: List of analysis objectives
        **kwargs: Additional configuration fields
    """
    config = {
        "name": name,
        "type": agent_type,
        "enabled": True,
        "objectives": objectives,
        "scope": {
            "paths": ["**/*.py"],
            "exclude_paths": ["**/__pycache__/**", "**/.venv/**"],
        },
        "token_budget": {
            "max_per_query": kwargs.get("max_per_query", 6500),
            "max_total": kwargs.get("max_total", 50000),
            "context_ratio": kwargs.get("context_ratio", 0.7),
        },
        "memory_policy": {
            "type": kwargs.get("memory_type", "session"),
            "max_entries": kwargs.get("max_entries", 100),
        },
        "provider": {
            "name": kwargs.get("provider", "ollama"),
            "model": kwargs.get("model", "qwen2.5-opencode:7b"),
            "temperature": kwargs.get("temperature", 0.3),
        },
    }

    # Add any extra fields
    for key in ["output", "automation"]:
        if key in kwargs:
            config[key] = kwargs[key]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
