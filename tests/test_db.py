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
        self.params = None

    def execute(self, sql, params=None):
        self.executed = sql
        self.params = params

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


def test_fetch_rows_passes_params():
    cursor = FakeCursor(
        description=[("ACCOUNT_ID",)],
        rows=[(7,)],
    )
    table = fetch_rows(
        cursor,
        "SELECT ACCOUNT_ID FROM ACCOUNTS WHERE SIP_ID = :sip_id",
        limit=10,
        params={"sip_id": "1001"},
    )
    assert cursor.params == {"sip_id": "1001"}
    assert table.columns == ["ACCOUNT_ID"]
    assert table.rows == [[7]]
