from datetime import datetime

import pytest

from oracle_rule_fetcher.cli import parse_args, run


class FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchmany(self, size):
        return self._rows[:size]


def _write_configs(tmp_path):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules.yaml").write_text(
        "global_limit: 100\n"
        "rules:\n"
        "  - name: active_customers\n"
        "    enabled: true\n"
        "    config: rules/active_customers.yaml\n"
        "  - name: disabled_rule\n"
        "    enabled: false\n"
        "    config: rules/disabled_rule.yaml\n"
    )
    (tmp_path / "rules" / "active_customers.yaml").write_text(
        "sql: SELECT CUST_ID, CUST_NAME FROM CUSTOMERS\n"
        "limit: 2\n"
        "column_mapping:\n"
        "  CUST_ID: customer_id\n"
        "  CUST_NAME: customer_name\n"
    )


def test_parse_args_defaults():
    args = parse_args(["--config", "config/rules.yaml"])
    assert args.config == "config/rules.yaml"
    assert args.output_dir == "output"
    assert args.log_file == "run.log"


def test_run_writes_csv_and_log_for_enabled_rules(tmp_path):
    _write_configs(tmp_path)
    output_dir = tmp_path / "output"
    log_file = tmp_path / "run.log"

    cursor = FakeCursor(
        description=[("CUST_ID",), ("CUST_NAME",)],
        rows=[(1, "Alice"), (2, "Bob"), (3, "Carol")],
    )

    exit_code = run(
        parent_path=tmp_path / "rules.yaml",
        output_dir=output_dir,
        log_file=log_file,
        cursor_provider=lambda: cursor,
        now=lambda: datetime(2026, 8, 17, 14, 30, 0),
    )

    assert exit_code == 0

    csv_path = output_dir / "active_customers.csv"
    assert csv_path.exists()
    content = csv_path.read_text()
    assert "customer_id,customer_name,fetched_at" in content
    assert "1,Alice,2026-08-17T14:30:00" in content
    # limit=2 applied
    assert "Carol" not in content
    # disabled rule produced no file
    assert not (output_dir / "disabled_rule.csv").exists()

    log_content = log_file.read_text()
    assert "active_customers" in log_content


def test_run_isolates_failing_rule(tmp_path):
    _write_configs(tmp_path)
    output_dir = tmp_path / "output"
    log_file = tmp_path / "run.log"

    class FailingCursor(FakeCursor):
        def execute(self, sql, params=None):
            raise RuntimeError("ORA-00942: table or view does not exist")

    exit_code = run(
        parent_path=tmp_path / "rules.yaml",
        output_dir=output_dir,
        log_file=log_file,
        cursor_provider=lambda: FailingCursor(description=[], rows=[]),
        now=lambda: datetime(2026, 8, 17, 14, 30, 0),
    )

    # A single rule failure does not abort the run, but signals failure via exit code
    assert exit_code == 1
    assert "ORA-00942" in log_file.read_text()


def test_run_propagates_write_csv_failure(tmp_path, monkeypatch):
    _write_configs(tmp_path)
    output_dir = tmp_path / "output"
    log_file = tmp_path / "run.log"

    cursor = FakeCursor(
        description=[("CUST_ID",), ("CUST_NAME",)],
        rows=[(1, "Alice")],
    )

    import oracle_rule_fetcher.cli as cli_mod

    monkeypatch.setattr(cli_mod, "write_csv", lambda table, path: (_ for _ in ()).throw(IOError("disk full")))

    with pytest.raises(IOError, match="disk full"):
        run(
            parent_path=tmp_path / "rules.yaml",
            output_dir=output_dir,
            log_file=log_file,
            cursor_provider=lambda: cursor,
            now=lambda: datetime(2026, 8, 17, 14, 30, 0),
        )


from oracle_rule_fetcher.config import ConfigError


class CsvModeCursor:
    def __init__(self):
        self.description = [("ACCOUNT_ID",), ("BALANCE",)]
        self._current = []

    def execute(self, sql, params=None):
        sip = params["sip_id"]
        self._current = [(int(sip), int(sip) * 10)]

    def fetchmany(self, size):
        return self._current[:size]


def _write_csv_mode_configs(tmp_path):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules.yaml").write_text(
        "global_limit: 100\n"
        "rules:\n"
        "  - name: rsb_sip\n"
        "    enabled: true\n"
        "    config: rules/rsb_sip.yaml\n"
    )
    (tmp_path / "rules" / "rsb_sip.yaml").write_text(
        "sql: SELECT ACCOUNT_ID, BALANCE FROM ACCOUNTS WHERE SIP_ID = :sip_id\n"
        "column_mapping:\n"
        "  ACCOUNT_ID: account_id\n"
        "  BALANCE: balance\n"
    )
    (tmp_path / "alm_apo.csv").write_text("1001,EMEA,APO\n1002,APAC,ALM\n1003,AMER,APO\n")
    (tmp_path / "input_config.yaml").write_text(
        "inputs:\n"
        "  rsb_sip:\n"
        f"    file: {tmp_path / 'alm_apo.csv'}\n"
        "    column_headers_exist: false\n"
        "    filter_columns:\n"
        "      - column: 3\n"
        "        operator: eq\n"
        "        value: APO\n"
        "    query_parameters:\n"
        "      1: sip_id\n"
        "      2: region\n"
    )


def test_parse_args_input_config_default():
    args = parse_args(["--config", "config/rules.yaml"])
    assert args.input_config == "config/input_config.yaml"


def test_run_csv_mode_writes_combined_output(tmp_path):
    _write_csv_mode_configs(tmp_path)
    output_dir = tmp_path / "output"

    exit_code = run(
        parent_path=tmp_path / "rules.yaml",
        output_dir=output_dir,
        log_file=tmp_path / "run.log",
        cursor_provider=CsvModeCursor,
        input_config_path=tmp_path / "input_config.yaml",
        now=lambda: datetime(2026, 8, 31, 12, 0, 0),
    )

    assert exit_code == 0
    content = (output_dir / "rsb_sip.csv").read_text()
    assert "sip_id,region,account_id,balance,fetched_at,error" in content
    # filter kept APO rows only (1001, 1003), not 1002
    assert "1001,EMEA,1001,10010,2026-08-31T12:00:00," in content
    assert "1003,AMER,1003,10030,2026-08-31T12:00:00," in content
    assert "1002" not in content


def test_run_normal_mode_unaffected_when_no_input_entry(tmp_path):
    _write_configs(tmp_path)
    output_dir = tmp_path / "output"
    cursor = FakeCursor(description=[("CUST_ID",), ("CUST_NAME",)], rows=[(1, "Alice")])

    exit_code = run(
        parent_path=tmp_path / "rules.yaml",
        output_dir=output_dir,
        log_file=tmp_path / "run.log",
        cursor_provider=lambda: cursor,
        input_config_path=None,
        now=lambda: datetime(2026, 8, 17, 14, 30, 0),
    )

    assert exit_code == 0
    content = (output_dir / "active_customers.csv").read_text()
    assert "customer_id,customer_name,fetched_at" in content
    assert "error" not in content


def test_run_fails_fast_on_input_config_mismatch(tmp_path):
    _write_configs(tmp_path)
    (tmp_path / "input_config.yaml").write_text(
        "inputs:\n"
        "  ghost_rule:\n"
        "    file: x.csv\n"
        "    column_headers_exist: false\n"
    )

    with pytest.raises(ConfigError, match="ghost_rule"):
        run(
            parent_path=tmp_path / "rules.yaml",
            output_dir=tmp_path / "output",
            log_file=tmp_path / "run.log",
            cursor_provider=lambda: FakeCursor(description=[], rows=[]),
            input_config_path=tmp_path / "input_config.yaml",
            now=lambda: datetime(2026, 8, 17, 14, 30, 0),
        )


def test_run_csv_mode_logs_skipped_records(tmp_path):
    _write_csv_mode_configs(tmp_path)
    output_dir = tmp_path / "output"
    log_file = tmp_path / "run.log"

    class PartiallyFailingCursor:
        def __init__(self):
            self.description = [("ACCOUNT_ID",), ("BALANCE",)]
            self._current = []

        def execute(self, sql, params=None):
            sip = params["sip_id"]
            if sip == "1003":
                raise RuntimeError("ORA-00942: table or view does not exist")
            self._current = [(int(sip), int(sip) * 10)]

        def fetchmany(self, size):
            return self._current[:size]

    exit_code = run(
        parent_path=tmp_path / "rules.yaml",
        output_dir=output_dir,
        log_file=log_file,
        cursor_provider=PartiallyFailingCursor,
        input_config_path=tmp_path / "input_config.yaml",
        now=lambda: datetime(2026, 8, 31, 12, 0, 0),
    )

    assert exit_code == 1
    content = (output_dir / "rsb_sip.csv").read_text()
    assert "Skipped-" in content

    log_content = log_file.read_text()
    assert "rsb_sip" in log_content
    assert "Skipped-" in log_content
