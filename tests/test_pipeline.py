from oracle_rule_fetcher.config import RuleConfig
from oracle_rule_fetcher.pipeline import build_rule_table


class FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows

    def execute(self, sql):
        self.sql = sql

    def fetchmany(self, size):
        return self._rows[:size]


def test_build_rule_table_applies_limit_mapping_and_timestamp():
    cursor = FakeCursor(
        description=[("CUST_ID",), ("CUST_NAME",)],
        rows=[(1, "Alice"), (2, "Bob"), (3, "Carol")],
    )
    rule = RuleConfig(
        name="active_customers",
        sql="SELECT CUST_ID, CUST_NAME FROM CUSTOMERS",
        limit=2,
        column_mapping={"CUST_ID": "customer_id", "CUST_NAME": "customer_name"},
    )
    table = build_rule_table(cursor, rule, global_limit=100, timestamp="2026-08-17T14:30:00")

    assert table.columns == ["customer_id", "customer_name", "fetched_at"]
    assert table.rows == [
        [1, "Alice", "2026-08-17T14:30:00"],
        [2, "Bob", "2026-08-17T14:30:00"],
    ]


def test_build_rule_table_falls_back_to_global_limit():
    cursor = FakeCursor(
        description=[("A",)],
        rows=[(1,), (2,), (3,), (4,)],
    )
    rule = RuleConfig(name="r", sql="SELECT A FROM T", limit=None)
    table = build_rule_table(cursor, rule, global_limit=3, timestamp="T")
    assert len(table.rows) == 3
