# src/oracle_rule_fetcher/input_config.py
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from oracle_rule_fetcher.config import ConfigError, ParentConfig

VALID_OPERATORS = frozenset({"eq", "ne", "in", "gt", "lt", "gte", "lte"})


@dataclass
class FilterCondition:
    column: int | str
    operator: str
    value: object


@dataclass
class InputEntry:
    name: str
    file: str
    column_headers_exist: bool
    filter_columns: list[FilterCondition] = field(default_factory=list)
    query_parameters: dict = field(default_factory=dict)


@dataclass
class InputConfig:
    inputs: dict[str, InputEntry] = field(default_factory=dict)


def _is_name(ref) -> bool:
    return isinstance(ref, str)


def load_input_config(path) -> InputConfig:
    if path is None:
        return InputConfig()
    path = Path(path)
    if not path.exists():
        return InputConfig()

    data = yaml.safe_load(path.read_text())
    if data is None:
        return InputConfig()
    if not isinstance(data, dict):
        raise ConfigError(f"Input config {path} must be a mapping")

    raw_inputs = data.get("inputs", {}) or {}
    if not isinstance(raw_inputs, dict):
        raise ConfigError(f"Input config {path} 'inputs' must be a mapping")

    inputs: dict[str, InputEntry] = {}
    for key, entry in raw_inputs.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"Input entry {key!r} must be a mapping")
        if "file" not in entry:
            raise ConfigError(f"Input entry {key!r} missing 'file'")
        if "column_headers_exist" not in entry:
            raise ConfigError(f"Input entry {key!r} missing 'column_headers_exist'")
        headers_exist = bool(entry["column_headers_exist"])

        raw_filters = entry.get("filter_columns") or []
        if not isinstance(raw_filters, list):
            raise ConfigError(f"Input entry {key!r} 'filter_columns' must be a list")
        filters: list[FilterCondition] = []
        for cond in raw_filters:
            if not isinstance(cond, dict):
                raise ConfigError(f"Input entry {key!r} filter condition must be a mapping")
            for req in ("column", "operator", "value"):
                if req not in cond:
                    raise ConfigError(f"Input entry {key!r} filter missing '{req}'")
            operator = cond["operator"]
            if operator not in VALID_OPERATORS:
                raise ConfigError(
                    f"Input entry {key!r} invalid operator {operator!r}; "
                    f"expected one of {sorted(VALID_OPERATORS)}"
                )
            column = cond["column"]
            if _is_name(column) and not headers_exist:
                raise ConfigError(
                    f"Input entry {key!r} filter column {column!r} is a header name "
                    f"but column_headers_exist is false"
                )
            filters.append(FilterCondition(column=column, operator=operator, value=cond["value"]))

        raw_params = entry.get("query_parameters") or {}
        if not isinstance(raw_params, dict):
            raise ConfigError(f"Input entry {key!r} 'query_parameters' must be a mapping")
        for col_ref in raw_params:
            if _is_name(col_ref) and not headers_exist:
                raise ConfigError(
                    f"Input entry {key!r} query_parameters column {col_ref!r} is a header "
                    f"name but column_headers_exist is false"
                )

        inputs[key] = InputEntry(
            name=key,
            file=entry["file"],
            column_headers_exist=headers_exist,
            filter_columns=filters,
            query_parameters=dict(raw_params),
        )

    return InputConfig(inputs=inputs)


def validate_input_config(
    input_config: InputConfig, parent: ParentConfig, base_dir: Path
) -> None:
    rule_configs = {rule.name: rule.config for rule in parent.rules}
    for key in input_config.inputs:
        if key not in rule_configs:
            raise ConfigError(
                f"Input config key '{key}' has no matching rule in the parent config"
            )
        rule_file = Path(base_dir) / rule_configs[key]
        if not rule_file.exists():
            raise ConfigError(
                f"Input config key '{key}' rule file {rule_file} does not exist"
            )
