import pytest

from oracle_rule_fetcher.config import ConfigError
from oracle_rule_fetcher.csv_source import (
    CsvRecord,
    input_column_names,
    load_csv_records,
)
from oracle_rule_fetcher.input_config import FilterCondition, InputEntry


def _entry(tmp_path, text, **kwargs):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(text)
    defaults = dict(
        name="r",
        file=str(csv_path),
        column_headers_exist=False,
        filter_columns=[],
        query_parameters={1: "sip_id", 2: "region"},
    )
    defaults.update(kwargs)
    return InputEntry(**defaults)


def test_input_column_names_uses_bind_names():
    entry = InputEntry("r", "f.csv", False, [], {1: "sip_id", 2: "region"})
    assert input_column_names(entry) == ["sip_id", "region"]


def test_load_records_no_headers_by_number(tmp_path):
    entry = _entry(tmp_path, "1001,EMEA,APO\n1002,APAC,ALM\n")
    records = load_csv_records(entry)
    assert records == [
        CsvRecord(binds={"sip_id": "1001", "region": "EMEA"}, input_values=["1001", "EMEA"]),
        CsvRecord(binds={"sip_id": "1002", "region": "APAC"}, input_values=["1002", "APAC"]),
    ]


def test_load_records_pipe_delimiter(tmp_path):
    entry = _entry(tmp_path, "1001|EMEA|APO\n1002|APAC|ALM\n", delimiter="|")
    records = load_csv_records(entry)
    assert records == [
        CsvRecord(binds={"sip_id": "1001", "region": "EMEA"}, input_values=["1001", "EMEA"]),
        CsvRecord(binds={"sip_id": "1002", "region": "APAC"}, input_values=["1002", "APAC"]),
    ]


def test_pipe_delimiter_filter_applies(tmp_path):
    entry = _entry(
        tmp_path,
        "1001|EMEA|APO\n1002|APAC|ALM\n1003|AMER|APO\n",
        delimiter="|",
        filter_columns=[FilterCondition(column=3, operator="eq", value="APO")],
    )
    records = load_csv_records(entry)
    assert [r.input_values[0] for r in records] == ["1001", "1003"]


def test_load_records_with_headers_by_name(tmp_path):
    entry = _entry(
        tmp_path,
        "sip,reg,kind\n1001,EMEA,APO\n",
        column_headers_exist=True,
        query_parameters={"sip": "sip_id", "reg": "region"},
    )
    records = load_csv_records(entry)
    assert records == [
        CsvRecord(binds={"sip_id": "1001", "region": "EMEA"}, input_values=["1001", "EMEA"])
    ]


def test_filter_eq_keeps_matching_rows(tmp_path):
    entry = _entry(
        tmp_path,
        "1001,EMEA,APO\n1002,APAC,ALM\n1003,AMER,APO\n",
        filter_columns=[FilterCondition(column=3, operator="eq", value="APO")],
    )
    records = load_csv_records(entry)
    assert [r.input_values[0] for r in records] == ["1001", "1003"]


def test_filter_in_and_ne(tmp_path):
    entry = _entry(
        tmp_path,
        "1001,EMEA,APO\n1002,APAC,ALM\n1003,AMER,APO\n",
        filter_columns=[
            FilterCondition(column=2, operator="in", value=["EMEA", "AMER"]),
            FilterCondition(column=3, operator="ne", value="ALM"),
        ],
    )
    records = load_csv_records(entry)
    assert [r.input_values[0] for r in records] == ["1001", "1003"]


def test_filter_numeric_comparison(tmp_path):
    entry = _entry(
        tmp_path,
        "1001,EMEA,5\n1002,APAC,20\n",
        filter_columns=[FilterCondition(column=3, operator="gt", value=10)],
    )
    records = load_csv_records(entry)
    assert [r.input_values[0] for r in records] == ["1002"]


def test_no_filter_keeps_all(tmp_path):
    entry = _entry(tmp_path, "1001,EMEA,APO\n1002,APAC,ALM\n")
    assert len(load_csv_records(entry)) == 2


def test_number_out_of_range_raises(tmp_path):
    entry = _entry(tmp_path, "1001\n", query_parameters={5: "sip_id"})
    with pytest.raises(ConfigError, match="out of range"):
        load_csv_records(entry)


def test_unknown_name_raises(tmp_path):
    entry = _entry(
        tmp_path,
        "sip,reg\n1001,EMEA\n",
        column_headers_exist=True,
        query_parameters={"missing": "sip_id"},
    )
    with pytest.raises(ConfigError, match="Unknown column"):
        load_csv_records(entry)


def test_missing_file_raises_filenotfound():
    entry = InputEntry("r", "nope.csv", False, [], {1: "sip_id"})
    with pytest.raises(FileNotFoundError):
        load_csv_records(entry)
