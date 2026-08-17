import argparse
import os
from datetime import datetime
from pathlib import Path

from oracle_rule_fetcher.app_logging import configure_logging
from oracle_rule_fetcher.config import load_parent_config, load_rule_config
from oracle_rule_fetcher.db import OracleClient, load_db_settings
from oracle_rule_fetcher.export import write_csv
from oracle_rule_fetcher.pipeline import build_rule_table
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
    now=datetime.now,
) -> int:
    parent_path = Path(parent_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = configure_logging(log_file)
    parent = load_parent_config(parent_path)
    base_dir = parent_path.parent

    for entry in select_enabled(parent):
        try:
            rule = load_rule_config(base_dir / entry.config, entry.name)
            cursor = cursor_provider()
            timestamp = now().isoformat()
            table = build_rule_table(cursor, rule, parent.global_limit, timestamp)
            print(render_table(table))
            csv_path = output_dir / f"{entry.name}.csv"
            write_csv(table, csv_path)
            logger.info(
                "Rule %s: %d rows written to %s",
                entry.name,
                len(table.rows),
                csv_path,
            )
        except Exception as exc:  # isolate per-rule failures
            logger.error("Rule %s failed: %s", entry.name, exc)

    return 0


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
        )
    finally:
        client.close()
