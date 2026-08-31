# tests/test_input_config.py
from pathlib import Path

import pytest

from oracle_rule_fetcher.config import ConfigError, RuleRegistryEntry, ParentConfig
from oracle_rule_fetcher.input_config import (
    FilterCondition,
    InputConfig,
    InputEntry,
    load_input_config,
    validate_input_config,
)

INPUT_YAML = """\
inputs:
  rsb_sip:
    file: input/rsb/alm_apo.csv
    column_headers_exist: false
    filter_columns:
      - column: 3
        operator: eq
        value: "APO"
    query_parameters:
      1: sip_id
      2: region
"""


def test_load_input_config_parses_entry(tmp_path):
    path = tmp_path / "input_config.yaml"
    path.write_text(INPUT_YAML)
    cfg = load_input_config(path)
    assert isinstance(cfg, InputConfig)
    entry = cfg.inputs["rsb_sip"]
    assert entry.name == "rsb_sip"
    assert entry.file == "input/rsb/alm_apo.csv"
    assert entry.column_headers_exist is False
    assert entry.filter_columns == [FilterCondition(column=3, operator="eq", value="APO")]
    assert entry.query_parameters == {1: "sip_id", 2: "region"}


def test_load_input_config_missing_file_returns_empty():
    cfg = load_input_config("does_not_exist.yaml")
    assert cfg.inputs == {}


def test_load_input_config_none_returns_empty():
    cfg = load_input_config(None)
    assert cfg.inputs == {}


def test_load_input_config_bad_inputs_type_raises(tmp_path):
    path = tmp_path / "input_config.yaml"
    path.write_text("inputs: not_a_mapping\n")
    with pytest.raises(ConfigError, match="inputs"):
        load_input_config(path)


def test_load_input_config_invalid_operator_raises(tmp_path):
    path = tmp_path / "input_config.yaml"
    path.write_text(
        "inputs:\n"
        "  r:\n"
        "    file: f.csv\n"
        "    column_headers_exist: false\n"
        "    filter_columns:\n"
        "      - column: 1\n"
        "        operator: bogus\n"
        "        value: x\n"
    )
    with pytest.raises(ConfigError, match="operator"):
        load_input_config(path)


def test_load_input_config_name_reference_without_headers_raises(tmp_path):
    path = tmp_path / "input_config.yaml"
    path.write_text(
        "inputs:\n"
        "  r:\n"
        "    file: f.csv\n"
        "    column_headers_exist: false\n"
        "    query_parameters:\n"
        "      cust_id: customer_id\n"
    )
    with pytest.raises(ConfigError, match="header"):
        load_input_config(path)


def _parent():
    return ParentConfig(
        global_limit=100,
        rules=[RuleRegistryEntry("rsb_sip", True, "rules/rsb_sip.yaml")],
    )


def test_validate_input_config_ok(tmp_path):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "rsb_sip.yaml").write_text("sql: SELECT 1 FROM DUAL\n")
    cfg = InputConfig(inputs={"rsb_sip": InputEntry("rsb_sip", "f.csv", False, [], {})})
    validate_input_config(cfg, _parent(), tmp_path)  # no raise


def test_validate_input_config_missing_rule_entry_raises(tmp_path):
    cfg = InputConfig(inputs={"ghost": InputEntry("ghost", "f.csv", False, [], {})})
    with pytest.raises(ConfigError, match="ghost"):
        validate_input_config(cfg, _parent(), tmp_path)


def test_validate_input_config_missing_rule_file_raises(tmp_path):
    cfg = InputConfig(inputs={"rsb_sip": InputEntry("rsb_sip", "f.csv", False, [], {})})
    with pytest.raises(ConfigError, match="rule file"):
        validate_input_config(cfg, _parent(), tmp_path)


def test_sample_input_config_validates():
    from oracle_rule_fetcher.config import load_parent_config

    root = Path(__file__).parent.parent
    parent = load_parent_config(root / "config" / "rules.yaml")
    cfg = load_input_config(root / "config" / "input_config.yaml")
    assert "rsb_sip" in cfg.inputs
    entry = cfg.inputs["rsb_sip"]
    assert entry.query_parameters == {1: "sip_id", 2: "region"}
    assert entry.delimiter == "|"
    validate_input_config(cfg, parent, root / "config")  # no raise


def test_load_input_config_delimiter_default_and_explicit(tmp_path):
    path = tmp_path / "input_config.yaml"
    path.write_text(
        "inputs:\n"
        "  a:\n"
        "    file: a.csv\n"
        "    column_headers_exist: false\n"
        "  b:\n"
        "    file: b.csv\n"
        "    column_headers_exist: false\n"
        "    delimiter: '|'\n"
    )
    cfg = load_input_config(path)
    assert cfg.inputs["a"].delimiter == ","
    assert cfg.inputs["b"].delimiter == "|"


def test_load_input_config_invalid_delimiter_raises(tmp_path):
    path = tmp_path / "input_config.yaml"
    path.write_text(
        "inputs:\n"
        "  a:\n"
        "    file: a.csv\n"
        "    column_headers_exist: false\n"
        "    delimiter: '||'\n"
    )
    with pytest.raises(ConfigError, match="delimiter"):
        load_input_config(path)
