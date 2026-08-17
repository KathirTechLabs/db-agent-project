from pathlib import Path

import pytest

from oracle_rule_fetcher.config import (
    ConfigError,
    ParentConfig,
    RuleConfig,
    RuleRegistryEntry,
    load_parent_config,
    load_rule_config,
)

PARENT_YAML = """\
global_limit: 100
rules:
  - name: active_customers
    enabled: true
    config: rules/active_customers.yaml
  - name: dormant_accounts
    enabled: false
    config: rules/dormant_accounts.yaml
"""

RULE_YAML = """\
sql: SELECT CUST_ID, CUST_NAME FROM CUSTOMERS WHERE STATUS = 'ACTIVE'
limit: 25
column_mapping:
  CUST_ID: customer_id
  CUST_NAME: customer_name
"""


def test_load_parent_config(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(PARENT_YAML)
    parent = load_parent_config(path)
    assert isinstance(parent, ParentConfig)
    assert parent.global_limit == 100
    assert parent.rules == [
        RuleRegistryEntry("active_customers", True, "rules/active_customers.yaml"),
        RuleRegistryEntry("dormant_accounts", False, "rules/dormant_accounts.yaml"),
    ]


def test_load_parent_config_missing_global_limit(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("rules: []\n")
    with pytest.raises(ConfigError, match="global_limit"):
        load_parent_config(path)


def test_load_parent_config_rule_missing_field(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("global_limit: 10\nrules:\n  - name: x\n    enabled: true\n")
    with pytest.raises(ConfigError, match="config"):
        load_parent_config(path)


def test_load_rule_config(tmp_path):
    path = tmp_path / "rule.yaml"
    path.write_text(RULE_YAML)
    rule = load_rule_config(path, "active_customers")
    assert isinstance(rule, RuleConfig)
    assert rule.name == "active_customers"
    assert rule.sql.startswith("SELECT CUST_ID")
    assert rule.limit == 25
    assert rule.column_mapping == {"CUST_ID": "customer_id", "CUST_NAME": "customer_name"}


def test_load_rule_config_defaults(tmp_path):
    path = tmp_path / "rule.yaml"
    path.write_text("sql: SELECT 1 FROM DUAL\n")
    rule = load_rule_config(path, "trivial")
    assert rule.limit is None
    assert rule.column_mapping == {}


def test_load_rule_config_missing_sql(tmp_path):
    path = tmp_path / "rule.yaml"
    path.write_text("limit: 5\n")
    with pytest.raises(ConfigError, match="sql"):
        load_rule_config(path, "broken")


def test_sample_parent_config_is_valid():
    config_path = Path(__file__).parent.parent / "config" / "rules.yaml"
    parent = load_parent_config(config_path)
    assert parent.global_limit >= 1
    assert any(r.name == "active_customers" for r in parent.rules)


def test_load_parent_config_file_not_found():
    with pytest.raises(ConfigError, match="not found"):
        load_parent_config("nonexistent.yaml")


def test_load_parent_config_empty_file(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("")
    with pytest.raises(ConfigError, match="is empty"):
        load_parent_config(path)


def test_load_parent_config_non_numeric_global_limit(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("global_limit: not_a_number\n")
    with pytest.raises(ConfigError, match="global_limit.*numeric"):
        load_parent_config(path)


def test_load_parent_config_non_list_rules(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("global_limit: 10\nrules: foo\n")
    with pytest.raises(ConfigError, match="rules.*list"):
        load_parent_config(path)


def test_load_parent_config_non_dict_rule_entry(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("global_limit: 10\nrules:\n  - null\n")
    with pytest.raises(ConfigError, match="dict"):
        load_parent_config(path)


def test_load_rule_config_file_not_found():
    with pytest.raises(ConfigError, match="not found"):
        load_rule_config("nonexistent.yaml", "test")


def test_load_rule_config_empty_file(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("")
    with pytest.raises(ConfigError, match="is empty"):
        load_rule_config(path, "test")


def test_load_rule_config_non_numeric_limit(tmp_path):
    path = tmp_path / "rule.yaml"
    path.write_text("sql: SELECT 1 FROM DUAL\nlimit: not_a_number\n")
    with pytest.raises(ConfigError, match="limit.*numeric"):
        load_rule_config(path, "broken")


def test_load_rule_config_non_dict_column_mapping(tmp_path):
    path = tmp_path / "rule.yaml"
    path.write_text("sql: SELECT 1 FROM DUAL\ncolumn_mapping: foo\n")
    with pytest.raises(ConfigError, match="column_mapping.*dict"):
        load_rule_config(path, "broken")
