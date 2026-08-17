import csv
from pathlib import Path

from oracle_rule_fetcher.models import Table


def write_csv(table: Table, path: str | Path) -> None:
    path = Path(path)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(table.columns)
        writer.writerows(table.rows)
