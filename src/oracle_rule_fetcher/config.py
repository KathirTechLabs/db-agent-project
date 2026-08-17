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
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError as e:
        raise ConfigError(f"Parent config {path} not found") from e
    if data is None:
        raise ConfigError(f"Parent config {path} is empty")
    if not isinstance(data, dict):
        raise ConfigError(f"Parent config {path} must be a mapping")
    if "global_limit" not in data:
        raise ConfigError(f"Parent config {path} missing 'global_limit'")

    rules_data = data.get("rules", []) or []
    if not isinstance(rules_data, list):
        raise ConfigError(f"Parent config {path} 'rules' must be a list")
    
    rules: list[RuleRegistryEntry] = []
    for entry in rules_data:
        if not isinstance(entry, dict):
            raise ConfigError(f"Rule entry {entry!r} must be a dict")
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
    try:
        global_limit = int(data["global_limit"])
    except (ValueError, TypeError) as e:
        raise ConfigError(f"Parent config {path} 'global_limit' must be numeric") from e
    return ParentConfig(global_limit=global_limit, rules=rules)


def load_rule_config(path: str | Path, name: str) -> RuleConfig:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError as e:
        raise ConfigError(f"Rule config {path} not found") from e
    if data is None:
        raise ConfigError(f"Rule config {path} is empty")
    if not isinstance(data, dict):
        raise ConfigError(f"Rule config {path} must be a mapping")
    if "sql" not in data:
        raise ConfigError(f"Rule config {path} missing 'sql'")

    limit = data.get("limit")
    if limit is not None:
        try:
            limit = int(limit)
        except (ValueError, TypeError) as e:
            raise ConfigError(f"Rule config {path} 'limit' must be numeric") from e
    
    cm = data.get("column_mapping")
    if cm is not None and not isinstance(cm, dict):
        raise ConfigError(f"Rule config {path} 'column_mapping' must be a dict")
    
    return RuleConfig(
        name=name,
        sql=data["sql"],
        limit=limit,
        column_mapping=cm or {},
    )
