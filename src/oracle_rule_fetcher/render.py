from tabulate import tabulate

from oracle_rule_fetcher.models import Table


def render_table(table: Table) -> str:
    return tabulate(table.rows, headers=table.columns, tablefmt="grid")
