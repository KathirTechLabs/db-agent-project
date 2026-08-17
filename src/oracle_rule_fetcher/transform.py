from oracle_rule_fetcher.models import Table


def apply_column_mapping(table: Table, mapping: dict[str, str]) -> Table:
    columns = [mapping.get(name, name) for name in table.columns]
    return Table(columns=columns, rows=[list(row) for row in table.rows])


def add_timestamp_column(
    table: Table, timestamp: str, column_name: str = "fetched_at"
) -> Table:
    columns = table.columns + [column_name]
    rows = [list(row) + [timestamp] for row in table.rows]
    return Table(columns=columns, rows=rows)
