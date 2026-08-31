import csv
from dataclasses import dataclass
from pathlib import Path

from oracle_rule_fetcher.config import ConfigError
from oracle_rule_fetcher.input_config import FilterCondition, InputEntry


@dataclass
class CsvRecord:
    binds: dict
    input_values: list


def input_column_names(entry: InputEntry) -> list[str]:
    return [str(name) for name in entry.query_parameters.values()]


def _resolve_index(ref, headers: list[str], headers_exist: bool) -> int:
    if isinstance(ref, bool):
        raise ConfigError(f"Column reference {ref!r} must be a number or name")
    if isinstance(ref, int):
        return ref - 1
    if not headers_exist:
        raise ConfigError(
            f"Column name {ref!r} requires column_headers_exist: true"
        )
    try:
        return headers.index(ref)
    except ValueError as exc:
        raise ConfigError(f"Unknown column name {ref!r} in CSV header") from exc


def _cell(row: list[str], ref, headers: list[str], headers_exist: bool):
    idx = _resolve_index(ref, headers, headers_exist)
    if idx < 0 or idx >= len(row):
        raise ConfigError(f"Column reference {ref!r} out of range for row {row!r}")
    return row[idx]


def _coerce(cell, value):
    try:
        return float(cell), float(value)
    except (TypeError, ValueError):
        return str(cell), str(value)


def _matches(cell, operator: str, value) -> bool:
    if operator == "eq":
        return str(cell) == str(value)
    if operator == "ne":
        return str(cell) != str(value)
    if operator == "in":
        return str(cell) in [str(v) for v in value]
    left, right = _coerce(cell, value)
    if operator == "gt":
        return left > right
    if operator == "lt":
        return left < right
    if operator == "gte":
        return left >= right
    if operator == "lte":
        return left <= right
    raise ConfigError(f"Unknown operator {operator!r}")


def _passes(row: list[str], conditions: list[FilterCondition], headers, headers_exist) -> bool:
    for cond in conditions:
        cell = _cell(row, cond.column, headers, headers_exist)
        if not _matches(cell, cond.operator, cond.value):
            return False
    return True


def load_csv_records(entry: InputEntry) -> list[CsvRecord]:
    with Path(entry.file).open(newline="") as f:
        rows = list(csv.reader(f))

    headers: list[str] = []
    if entry.column_headers_exist:
        if not rows:
            return []
        headers = rows[0]
        rows = rows[1:]

    records: list[CsvRecord] = []
    for row in rows:
        if not _passes(row, entry.filter_columns, headers, entry.column_headers_exist):
            continue
        binds: dict = {}
        input_values: list = []
        for col_ref, bind_name in entry.query_parameters.items():
            value = _cell(row, col_ref, headers, entry.column_headers_exist)
            binds[str(bind_name)] = value
            input_values.append(value)
        records.append(CsvRecord(binds=binds, input_values=input_values))
    return records
