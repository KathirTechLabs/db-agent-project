from oracle_rule_fetcher.config import RuleConfig
from oracle_rule_fetcher.csv_source import CsvRecord, input_column_names
from oracle_rule_fetcher.db import fetch_rows
from oracle_rule_fetcher.input_config import InputEntry
from oracle_rule_fetcher.models import Table
from oracle_rule_fetcher.rules import effective_limit
from oracle_rule_fetcher.transform import add_timestamp_column, apply_column_mapping


def build_rule_table(
    cursor, rule: RuleConfig, global_limit: int, timestamp: str
) -> Table:
    limit = effective_limit(rule, global_limit)
    table = fetch_rows(cursor, rule.sql, limit)
    table = apply_column_mapping(table, rule.column_mapping)
    return add_timestamp_column(table, timestamp)


def build_rule_table_from_csv(
    cursor,
    rule: RuleConfig,
    entry: InputEntry,
    records: list[CsvRecord],
    global_limit: int,
    timestamp: str,
) -> tuple[Table, bool]:
    limit = effective_limit(rule, global_limit)
    input_headers = input_column_names(entry)

    result_columns: list[str] | None = None
    staged: list[tuple[list, list | None, str]] = []
    had_errors = False

    for record in records:
        try:
            result = fetch_rows(cursor, rule.sql, limit, record.binds)
            if result_columns is None:
                result_columns = result.columns
            if result.rows:
                for row in result.rows:
                    staged.append((record.input_values, row, ""))
            else:
                staged.append((record.input_values, None, ""))
        except Exception as exc:  # isolate a single record's query failure
            had_errors = True
            staged.append((record.input_values, None, f"Skipped-{exc}"))

    mapped_columns = [
        rule.column_mapping.get(col, col) for col in (result_columns or [])
    ]
    n_result = len(mapped_columns)
    columns = input_headers + mapped_columns + ["fetched_at", "error"]

    rows: list[list] = []
    for input_values, result_row, error in staged:
        result_part = list(result_row) if result_row is not None else [""] * n_result
        rows.append(list(input_values) + result_part + [timestamp, error])

    return Table(columns=columns, rows=rows), had_errors
