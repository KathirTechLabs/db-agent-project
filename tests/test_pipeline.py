from oracle_rule_fetcher.config import RuleConfig
from oracle_rule_fetcher.csv_source import CsvRecord
from oracle_rule_fetcher.input_config import InputEntry
from oracle_rule_fetcher.pipeline import build_rule_table, build_rule_table_from_csv


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


class MappedCursor:
    """Returns rows keyed by the :sip_id bind; raises for sip_ids in `failing`."""

    def __init__(self, description, result_map, failing=()):
        self.description = description
        self._result_map = result_map
        self._failing = set(failing)
        self._current = []

    def execute(self, sql, params=None):
        sip = params["sip_id"]
        if sip in self._failing:
            raise RuntimeError(f"ORA-00942 for {sip}")
        self._current = self._result_map.get(sip, [])

    def fetchmany(self, size):
        return self._current[:size]


def _entry():
    return InputEntry(
        name="rsb_sip",
        file="x.csv",
        column_headers_exist=False,
        filter_columns=[],
        query_parameters={1: "sip_id", 2: "region"},
    )


def _rule():
    return RuleConfig(
        name="rsb_sip",
        sql="SELECT ACCOUNT_ID, BALANCE FROM ACCOUNTS WHERE SIP_ID = :sip_id",
        limit=None,
        column_mapping={"ACCOUNT_ID": "account_id", "BALANCE": "balance"},
    )


def test_csv_table_one_row_per_record():
    cursor = MappedCursor(
        description=[("ACCOUNT_ID",), ("BALANCE",)],
        result_map={"1001": [(11, 100)], "1003": [(33, 300)]},
    )
    records = [
        CsvRecord(binds={"sip_id": "1001", "region": "EMEA"}, input_values=["1001", "EMEA"]),
        CsvRecord(binds={"sip_id": "1003", "region": "AMER"}, input_values=["1003", "AMER"]),
    ]
    table, had_errors = build_rule_table_from_csv(
        cursor, _rule(), _entry(), records, global_limit=100, timestamp="T"
    )
    assert had_errors is False
    assert table.columns == ["sip_id", "region", "account_id", "balance", "fetched_at", "error"]
    assert table.rows == [
        ["1001", "EMEA", 11, 100, "T", ""],
        ["1003", "AMER", 33, 300, "T", ""],
    ]


def test_csv_table_multiple_rows_per_record():
    cursor = MappedCursor(
        description=[("ACCOUNT_ID",), ("BALANCE",)],
        result_map={"1001": [(11, 100), (12, 150)]},
    )
    records = [CsvRecord(binds={"sip_id": "1001", "region": "EMEA"}, input_values=["1001", "EMEA"])]
    table, had_errors = build_rule_table_from_csv(
        cursor, _rule(), _entry(), records, global_limit=100, timestamp="T"
    )
    assert had_errors is False
    assert table.rows == [
        ["1001", "EMEA", 11, 100, "T", ""],
        ["1001", "EMEA", 12, 150, "T", ""],
    ]


def test_csv_table_zero_rows_for_record():
    cursor = MappedCursor(description=[("ACCOUNT_ID",), ("BALANCE",)], result_map={"1001": []})
    records = [CsvRecord(binds={"sip_id": "1001", "region": "EMEA"}, input_values=["1001", "EMEA"])]
    table, had_errors = build_rule_table_from_csv(
        cursor, _rule(), _entry(), records, global_limit=100, timestamp="T"
    )
    assert had_errors is False
    assert table.rows == [["1001", "EMEA", "", "", "T", ""]]


def test_csv_table_failing_record_produces_skipped_row():
    cursor = MappedCursor(
        description=[("ACCOUNT_ID",), ("BALANCE",)],
        result_map={"1001": [(11, 100)]},
        failing={"1003"},
    )
    records = [
        CsvRecord(binds={"sip_id": "1001", "region": "EMEA"}, input_values=["1001", "EMEA"]),
        CsvRecord(binds={"sip_id": "1003", "region": "AMER"}, input_values=["1003", "AMER"]),
    ]
    table, had_errors = build_rule_table_from_csv(
        cursor, _rule(), _entry(), records, global_limit=100, timestamp="T"
    )
    assert had_errors is True
    assert table.rows[0] == ["1001", "EMEA", 11, 100, "T", ""]
    assert table.rows[1][:2] == ["1003", "AMER"]
    assert table.rows[1][2:4] == ["", ""]
    assert table.rows[1][4] == "T"
    assert table.rows[1][5].startswith("Skipped-")


def test_csv_table_all_records_fail_has_no_result_columns():
    cursor = MappedCursor(description=[], result_map={}, failing={"1001"})
    records = [CsvRecord(binds={"sip_id": "1001", "region": "EMEA"}, input_values=["1001", "EMEA"])]
    table, had_errors = build_rule_table_from_csv(
        cursor, _rule(), _entry(), records, global_limit=100, timestamp="T"
    )
    assert had_errors is True
    assert table.columns == ["sip_id", "region", "fetched_at", "error"]
    assert table.rows[0][:2] == ["1001", "EMEA"]
    assert table.rows[0][2] == "T"
    assert table.rows[0][3].startswith("Skipped-")
