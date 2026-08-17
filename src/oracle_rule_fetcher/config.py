from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised when a config file is missing or malformed."""


@dataclass
class RuleRegistryEntry:
    name: str
    enabled: bool
    config: str


@dataclass
class ParentConfig:
    global_limit: int
    rules: list[RuleRegistryEntry]


@dataclass
class RuleConfig:
    name: str
    sql: str
    limit: int | None = None
    column_mapping: dict[str, str] = field(default_factory=dict)


def load_parent_config(path: str | Path) -> ParentConfig:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ConfigError(f"Parent config {path} must be a mapping")
    if "global_limit" not in data:
        raise ConfigError(f"Parent config {path} missing 'global_limit'")

    rules: list[RuleRegistryEntry] = []
    for entry in data.get("rules", []) or []:
        for key in ("name", "enabled", "config"):
            if key not in entry:
                raise ConfigError(f"Rule entry {entry!r} missing '{key}'")
        rules.append(
            RuleRegistryEntry(
                name=entry["name"],
                enabled=bool(entry["enabled"]),
                config=entry["config"],
            )
        )
    return ParentConfig(global_limit=int(data["global_limit"]), rules=rules)


def load_rule_config(path: str | Path, name: str) -> RuleConfig:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ConfigError(f"Rule config {path} must be a mapping")
    if "sql" not in data:
        raise ConfigError(f"Rule config {path} missing 'sql'")

    limit = data.get("limit")
    return RuleConfig(
        name=name,
        sql=data["sql"],
        limit=None if limit is None else int(limit),
        column_mapping=data.get("column_mapping") or {},
    )
