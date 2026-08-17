from oracle_rule_fetcher.models import Table
from oracle_rule_fetcher.render import render_table


def test_render_table_includes_headers_and_values():
    table = Table(columns=["customer_id", "customer_name"], rows=[[1, "Alice"]])
    output = render_table(table)
    assert "customer_id" in output
    assert "customer_name" in output
    assert "Alice" in output


def test_render_table_empty_rows_still_shows_headers():
    table = Table(columns=["customer_id"], rows=[])
    output = render_table(table)
    assert "customer_id" in output
