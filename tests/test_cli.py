from datetime import datetime

from oracle_rule_fetcher.cli import parse_args, run


class FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows

    def execute(self, sql):
        self.sql = sql

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
        def execute(self, sql):
            raise RuntimeError("ORA-00942: table or view does not exist")

    exit_code = run(
        parent_path=tmp_path / "rules.yaml",
        output_dir=output_dir,
        log_file=log_file,
        cursor_provider=lambda: FailingCursor(description=[], rows=[]),
        now=lambda: datetime(2026, 8, 17, 14, 30, 0),
    )

    # A single rule failure does not abort the run
    assert exit_code == 0
    assert "ORA-00942" in log_file.read_text()
