import argparse
import os
from datetime import datetime
from pathlib import Path

from oracle_rule_fetcher.app_logging import configure_logging
from oracle_rule_fetcher.config import ConfigError, load_parent_config, load_rule_config
from oracle_rule_fetcher.csv_source import load_csv_records
from oracle_rule_fetcher.db import OracleClient, load_db_settings
from oracle_rule_fetcher.export import write_csv
from oracle_rule_fetcher.input_config import load_input_config, validate_input_config
from oracle_rule_fetcher.pipeline import build_rule_table, build_rule_table_from_csv
from oracle_rule_fetcher.render import render_table
from oracle_rule_fetcher.rules import select_enabled


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="oracle-rule-fetcher",
        description="Fetch Oracle data based on configurable rules.",
    )
    parser.add_argument(
        "--config", required=True, help="Path to the parent config file."
    )
    parser.add_argument(
        "--input-config",
        default="config/input_config.yaml",
        help="Path to the CSV input config file (optional; missing file = all rules normal mode).",
    )
    parser.add_argument(
        "--output-dir", default="output", help="Directory for CSV output."
    )
    parser.add_argument(
        "--log-file", default="run.log", help="Path to the run log file."
    )
    return parser.parse_args(argv)


def run(
    parent_path,
    output_dir,
    log_file,
    cursor_provider,
    input_config_path=None,
    now=datetime.now,
) -> int:
    parent_path = Path(parent_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = configure_logging(log_file)
    parent = load_parent_config(parent_path)
    base_dir = parent_path.parent

    input_config = load_input_config(input_config_path)
    validate_input_config(input_config, parent, base_dir)  # fail fast before DB work

    had_errors = False

    for entry in select_enabled(parent):
        rule = load_rule_config(base_dir / entry.config, entry.name)
        input_entry = input_config.inputs.get(entry.name)

        if input_entry is None:
            try:
                cursor = cursor_provider()
                timestamp = now().isoformat()
                table = build_rule_table(cursor, rule, parent.global_limit, timestamp)
            except Exception as exc:  # isolate Oracle/pipeline failures per-rule
                logger.error("Rule %s failed: %s", entry.name, exc)
                had_errors = True
                continue
        else:
            try:
                records = load_csv_records(input_entry)
            except ConfigError:
                raise  # bad column reference is run-level; abort
            except Exception as exc:  # missing CSV file etc. — isolate per-rule
                logger.error("Rule %s failed: %s", entry.name, exc)
                had_errors = True
                continue
            cursor = cursor_provider()
            timestamp = now().isoformat()
            table, rule_had_errors = build_rule_table_from_csv(
                cursor, rule, input_entry, records, parent.global_limit, timestamp
            )
            if rule_had_errors:
                had_errors = True
                error_idx = table.columns.index("error")
                for row in table.rows:
                    if row[error_idx]:
                        logger.warning("Rule %s record skipped: %s", entry.name, row[error_idx])

        print(render_table(table))
        csv_path = output_dir / f"{entry.name}.csv"
        write_csv(table, csv_path)
        logger.info(
            "Rule %s: %d rows written to %s",
            entry.name,
            len(table.rows),
            csv_path,
        )

    return 1 if had_errors else 0


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = load_db_settings(os.environ)
    client = OracleClient(settings)
    try:
        return run(
            parent_path=args.config,
            output_dir=args.output_dir,
            log_file=args.log_file,
            cursor_provider=client.cursor,
            input_config_path=args.input_config,
        )
    finally:
        client.close()
