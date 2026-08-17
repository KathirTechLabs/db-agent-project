from oracle_rule_fetcher.models import Table


def test_table_holds_columns_and_rows():
    table = Table(columns=["ID", "NAME"], rows=[[1, "Alice"], [2, "Bob"]])
    assert table.columns == ["ID", "NAME"]
    assert table.rows == [[1, "Alice"], [2, "Bob"]]
