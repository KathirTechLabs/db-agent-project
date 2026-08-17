from oracle_rule_fetcher.config import RuleConfig
from oracle_rule_fetcher.db import fetch_rows
from oracle_rule_fetcher.models import Table
from oracle_rule_fetcher.rules import effective_limit
from oracle_rule_fetcher.transform import add_timestamp_column, apply_column_mapping


def build_rule_table(
    cursor, rule: RuleConfig, global_limit: int, timestamp: str
) -> Table:
    limit = effective_limit(rule, global_limit)
    table = fetch_rows(cursor, rule.sql, limit)
    table = apply_column_mapping(table, rule.column_mapping)
    return add_timestamp_column(table, timestamp)
