"""Load and manage agent configurations."""

from pathlib import Path

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
            agent_name = config.type or config_file.stem
            agents.append((agent_name, config_file, config))
        except (ValueError, yaml.YAMLError) as e:
            print(f"Warning: Skipping invalid agent config {config_file}: {e}")

    return agents
