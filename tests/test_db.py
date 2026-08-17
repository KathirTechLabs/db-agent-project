import pytest

from oracle_rule_fetcher.db import (
    DbSettings,
    MissingEnvVarError,
    fetch_rows,
    load_db_settings,
)


class FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows
        self.executed = None

    def execute(self, sql):
        self.executed = sql

    def fetchmany(self, size):
        return self._rows[:size]


def test_load_db_settings_reads_env():
    env = {
        "ORACLE_USER": "scott",
        "ORACLE_PASSWORD": "tiger",
        "ORACLE_DSN": "localhost:1521/XEPDB1",
    }
    settings = load_db_settings(env)
    assert settings == DbSettings("scott", "tiger", "localhost:1521/XEPDB1")


def test_load_db_settings_missing_var_raises():
    env = {"ORACLE_USER": "scott", "ORACLE_PASSWORD": "tiger"}
    with pytest.raises(MissingEnvVarError, match="ORACLE_DSN"):
        load_db_settings(env)


def test_load_db_settings_empty_var_raises():
    env = {"ORACLE_USER": "", "ORACLE_PASSWORD": "tiger", "ORACLE_DSN": "d"}
    with pytest.raises(MissingEnvVarError, match="ORACLE_USER"):
        load_db_settings(env)


def test_fetch_rows_returns_table_with_columns_and_rows():
    cursor = FakeCursor(
        description=[("CUST_ID",), ("CUST_NAME",)],
        rows=[(1, "Alice"), (2, "Bob"), (3, "Carol")],
    )
    table = fetch_rows(cursor, "SELECT CUST_ID, CUST_NAME FROM CUSTOMERS", limit=2)
    assert cursor.executed == "SELECT CUST_ID, CUST_NAME FROM CUSTOMERS"
    assert table.columns == ["CUST_ID", "CUST_NAME"]
    assert table.rows == [[1, "Alice"], [2, "Bob"]]
