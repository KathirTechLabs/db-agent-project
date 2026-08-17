import csv

from oracle_rule_fetcher.export import write_csv
from oracle_rule_fetcher.models import Table


def test_write_csv_writes_header_and_rows(tmp_path):
    table = Table(
        columns=["customer_id", "fetched_at"],
        rows=[[1, "2026-08-17T14:30:00"], [2, "2026-08-17T14:30:00"]],
    )
    path = tmp_path / "active_customers.csv"
    write_csv(table, path)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["customer_id", "fetched_at"]
    assert rows[1] == ["1", "2026-08-17T14:30:00"]
    assert rows[2] == ["2", "2026-08-17T14:30:00"]
