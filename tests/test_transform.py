from oracle_rule_fetcher.models import Table
from oracle_rule_fetcher.transform import add_timestamp_column, apply_column_mapping


def test_apply_column_mapping_renames_mapped_columns():
    table = Table(columns=["CUST_ID", "CUST_NAME"], rows=[[1, "Alice"]])
    result = apply_column_mapping(table, {"CUST_ID": "customer_id", "CUST_NAME": "customer_name"})
    assert result.columns == ["customer_id", "customer_name"]
    assert result.rows == [[1, "Alice"]]


def test_apply_column_mapping_keeps_unmapped_columns():
    table = Table(columns=["CUST_ID", "EXTRA"], rows=[[1, "x"]])
    result = apply_column_mapping(table, {"CUST_ID": "customer_id"})
    assert result.columns == ["customer_id", "EXTRA"]


def test_add_timestamp_column_appends_value_to_every_row():
    table = Table(columns=["customer_id"], rows=[[1], [2]])
    result = add_timestamp_column(table, "2026-08-17T14:30:00", column_name="fetched_at")
    assert result.columns == ["customer_id", "fetched_at"]
    assert result.rows == [[1, "2026-08-17T14:30:00"], [2, "2026-08-17T14:30:00"]]


def test_add_timestamp_column_default_name():
    table = Table(columns=["a"], rows=[[1]])
    result = add_timestamp_column(table, "T")
    assert result.columns == ["a", "fetched_at"]
