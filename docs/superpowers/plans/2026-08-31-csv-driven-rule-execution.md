# CSV-Driven Rule Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let selected rules be driven by an input CSV file — filter rows, bind each surviving record's columns into the rule SQL, execute once per record, and aggregate all results (including error rows for failures) into one output CSV.

**Architecture:** Add two new modules (`input_config.py`, `csv_source.py`) and extend `db.py`, `pipeline.py`, `cli.py`. A new `config/input_config.yaml` maps a rule name to a CSV file, filters, and column→bind mappings. Rules with no input entry keep current single-query behavior.

**Tech Stack:** Python 3.11+, `uv`, `pytest`, `PyYAML`, `oracledb`, `tabulate`. Standard-library `csv` for input parsing.

## Global Constraints

- Python: `requires-python >= 3.11`.
- No new runtime dependencies — use the standard-library `csv` module.
- Config parsing uses `yaml.safe_load`; malformed config raises `ConfigError` (from `oracle_rule_fetcher.config`).
- CSV column numbers are **1-based** everywhere.
- `query_parameters` maps **CSV column (key: number or header name) → SQL reference variable (value: bind name without leading colon)**.
- Tests run with `uv run pytest`; `pythonpath = ["src"]` is already configured.
- Keep business logic out of `cli.py`; follow existing dataclass + module-boundary patterns.
- Every commit uses the repo's Conventional Commits style and includes the trailer:
  `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

---

## File Structure

- Create `src/oracle_rule_fetcher/input_config.py` — dataclasses (`FilterCondition`, `InputEntry`, `InputConfig`), `load_input_config`, `validate_input_config`, `VALID_OPERATORS`.
- Create `src/oracle_rule_fetcher/csv_source.py` — `CsvRecord`, `input_column_names`, `load_csv_records`, filtering/coercion helpers.
- Modify `src/oracle_rule_fetcher/db.py` — `fetch_rows` accepts optional `params`.
- Modify `src/oracle_rule_fetcher/pipeline.py` — add `build_rule_table_from_csv`.
- Modify `src/oracle_rule_fetcher/cli.py` — `--input-config` flag, startup validation, per-rule mode selection.
- Create tests: `tests/test_input_config.py`, `tests/test_csv_source.py`.
- Modify tests: `tests/test_db.py`, `tests/test_pipeline.py`, `tests/test_cli.py`.
- Create sample data/config: `config/input_config.yaml`, `config/rules/rsb_sip.yaml`, `input/rsb/alm_apo.csv`; modify `config/rules.yaml`; update `README.md`.

---

## Task 1: Input config model, loading, and startup validation

**Files:**
- Create: `src/oracle_rule_fetcher/input_config.py`
- Test: `tests/test_input_config.py`

**Interfaces:**
- Consumes: `ConfigError`, `ParentConfig` from `oracle_rule_fetcher.config`.
- Produces:
  - `VALID_OPERATORS: frozenset[str]` = `{"eq","ne","in","gt","lt","gte","lte"}`
  - `FilterCondition(column: int | str, operator: str, value)`
  - `InputEntry(name: str, file: str, column_headers_exist: bool, filter_columns: list[FilterCondition], query_parameters: dict[int | str, str])`
  - `InputConfig(inputs: dict[str, InputEntry])`
  - `load_input_config(path: str | Path | None) -> InputConfig` — `None`/missing file returns empty `InputConfig`; malformed raises `ConfigError`.
  - `validate_input_config(input_config: InputConfig, parent: ParentConfig, base_dir: Path) -> None` — raises `ConfigError` when a key has no matching rule or the rule file is missing.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_input_config.py -v`
Expected: FAIL with `ModuleNotFoundError: oracle_rule_fetcher.input_config`.

- [ ] **Step 3: Write the implementation**

```python
# src/oracle_rule_fetcher/input_config.py
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from oracle_rule_fetcher.config import ConfigError, ParentConfig

VALID_OPERATORS = frozenset({"eq", "ne", "in", "gt", "lt", "gte", "lte"})


@dataclass
class FilterCondition:
    column: int | str
    operator: str
    value: object


@dataclass
class InputEntry:
    name: str
    file: str
    column_headers_exist: bool
    filter_columns: list[FilterCondition] = field(default_factory=list)
    query_parameters: dict = field(default_factory=dict)


@dataclass
class InputConfig:
    inputs: dict[str, InputEntry] = field(default_factory=dict)


def _is_name(ref) -> bool:
    return isinstance(ref, str)


def load_input_config(path) -> InputConfig:
    if path is None:
        return InputConfig()
    path = Path(path)
    if not path.exists():
        return InputConfig()

    data = yaml.safe_load(path.read_text())
    if data is None:
        return InputConfig()
    if not isinstance(data, dict):
        raise ConfigError(f"Input config {path} must be a mapping")

    raw_inputs = data.get("inputs", {}) or {}
    if not isinstance(raw_inputs, dict):
        raise ConfigError(f"Input config {path} 'inputs' must be a mapping")

    inputs: dict[str, InputEntry] = {}
    for key, entry in raw_inputs.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"Input entry {key!r} must be a mapping")
        if "file" not in entry:
            raise ConfigError(f"Input entry {key!r} missing 'file'")
        if "column_headers_exist" not in entry:
            raise ConfigError(f"Input entry {key!r} missing 'column_headers_exist'")
        headers_exist = bool(entry["column_headers_exist"])

        raw_filters = entry.get("filter_columns") or []
        if not isinstance(raw_filters, list):
            raise ConfigError(f"Input entry {key!r} 'filter_columns' must be a list")
        filters: list[FilterCondition] = []
        for cond in raw_filters:
            if not isinstance(cond, dict):
                raise ConfigError(f"Input entry {key!r} filter condition must be a mapping")
            for req in ("column", "operator", "value"):
                if req not in cond:
                    raise ConfigError(f"Input entry {key!r} filter missing '{req}'")
            operator = cond["operator"]
            if operator not in VALID_OPERATORS:
                raise ConfigError(
                    f"Input entry {key!r} invalid operator {operator!r}; "
                    f"expected one of {sorted(VALID_OPERATORS)}"
                )
            column = cond["column"]
            if _is_name(column) and not headers_exist:
                raise ConfigError(
                    f"Input entry {key!r} filter column {column!r} is a header name "
                    f"but column_headers_exist is false"
                )
            filters.append(FilterCondition(column=column, operator=operator, value=cond["value"]))

        raw_params = entry.get("query_parameters") or {}
        if not isinstance(raw_params, dict):
            raise ConfigError(f"Input entry {key!r} 'query_parameters' must be a mapping")
        for col_ref in raw_params:
            if _is_name(col_ref) and not headers_exist:
                raise ConfigError(
                    f"Input entry {key!r} query_parameters column {col_ref!r} is a header "
                    f"name but column_headers_exist is false"
                )

        inputs[key] = InputEntry(
            name=key,
            file=entry["file"],
            column_headers_exist=headers_exist,
            filter_columns=filters,
            query_parameters=dict(raw_params),
        )

    return InputConfig(inputs=inputs)


def validate_input_config(
    input_config: InputConfig, parent: ParentConfig, base_dir: Path
) -> None:
    rule_configs = {rule.name: rule.config for rule in parent.rules}
    for key in input_config.inputs:
        if key not in rule_configs:
            raise ConfigError(
                f"Input config key '{key}' has no matching rule in the parent config"
            )
        rule_file = Path(base_dir) / rule_configs[key]
        if not rule_file.exists():
            raise ConfigError(
                f"Input config key '{key}' rule file {rule_file} does not exist"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_input_config.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/input_config.py tests/test_input_config.py
git commit -m "feat: add input_config loading and startup validation

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: CSV source — read, filter, and build per-record binds

**Files:**
- Create: `src/oracle_rule_fetcher/csv_source.py`
- Test: `tests/test_csv_source.py`

**Interfaces:**
- Consumes: `InputEntry`, `FilterCondition` from `oracle_rule_fetcher.input_config`; `ConfigError` from `oracle_rule_fetcher.config`.
- Produces:
  - `CsvRecord(binds: dict[str, object], input_values: list[object])`
  - `input_column_names(entry: InputEntry) -> list[str]` — the SQL reference variables (query_parameters values) in order, as strings.
  - `load_csv_records(entry: InputEntry) -> list[CsvRecord]` — reads `entry.file`, applies filters (AND), builds one `CsvRecord` per surviving row. Raises `ConfigError` for bad column references; lets `FileNotFoundError` propagate for a missing file.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_csv_source.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_csv_source.py -v`
Expected: FAIL with `ModuleNotFoundError: oracle_rule_fetcher.csv_source`.

- [ ] **Step 3: Write the implementation**

```python
# src/oracle_rule_fetcher/csv_source.py
import csv
from dataclasses import dataclass
from pathlib import Path

from oracle_rule_fetcher.config import ConfigError
from oracle_rule_fetcher.input_config import FilterCondition, InputEntry


@dataclass
class CsvRecord:
    binds: dict
    input_values: list


def input_column_names(entry: InputEntry) -> list[str]:
    return [str(name) for name in entry.query_parameters.values()]


def _resolve_index(ref, headers: list[str], headers_exist: bool) -> int:
    if isinstance(ref, bool):
        raise ConfigError(f"Column reference {ref!r} must be a number or name")
    if isinstance(ref, int):
        return ref - 1
    if not headers_exist:
        raise ConfigError(
            f"Column name {ref!r} requires column_headers_exist: true"
        )
    try:
        return headers.index(ref)
    except ValueError as exc:
        raise ConfigError(f"Unknown column name {ref!r} in CSV header") from exc


def _cell(row: list[str], ref, headers: list[str], headers_exist: bool):
    idx = _resolve_index(ref, headers, headers_exist)
    if idx < 0 or idx >= len(row):
        raise ConfigError(f"Column reference {ref!r} out of range for row {row!r}")
    return row[idx]


def _coerce(cell, value):
    try:
        return float(cell), float(value)
    except (TypeError, ValueError):
        return str(cell), str(value)


def _matches(cell, operator: str, value) -> bool:
    if operator == "eq":
        return str(cell) == str(value)
    if operator == "ne":
        return str(cell) != str(value)
    if operator == "in":
        return str(cell) in [str(v) for v in value]
    left, right = _coerce(cell, value)
    if operator == "gt":
        return left > right
    if operator == "lt":
        return left < right
    if operator == "gte":
        return left >= right
    if operator == "lte":
        return left <= right
    raise ConfigError(f"Unknown operator {operator!r}")


def _passes(row: list[str], conditions: list[FilterCondition], headers, headers_exist) -> bool:
    for cond in conditions:
        cell = _cell(row, cond.column, headers, headers_exist)
        if not _matches(cell, cond.operator, cond.value):
            return False
    return True


def load_csv_records(entry: InputEntry) -> list[CsvRecord]:
    with Path(entry.file).open(newline="") as f:
        rows = list(csv.reader(f))

    headers: list[str] = []
    if entry.column_headers_exist:
        if not rows:
            return []
        headers = rows[0]
        rows = rows[1:]

    records: list[CsvRecord] = []
    for row in rows:
        if not _passes(row, entry.filter_columns, headers, entry.column_headers_exist):
            continue
        binds: dict = {}
        input_values: list = []
        for col_ref, bind_name in entry.query_parameters.items():
            value = _cell(row, col_ref, headers, entry.column_headers_exist)
            binds[str(bind_name)] = value
            input_values.append(value)
        records.append(CsvRecord(binds=binds, input_values=input_values))
    return records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_csv_source.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/csv_source.py tests/test_csv_source.py
git commit -m "feat: add csv_source reader with filtering and per-record binds

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: `fetch_rows` accepts bind parameters

**Files:**
- Modify: `src/oracle_rule_fetcher/db.py` (function `fetch_rows`, lines 58-62)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `fetch_rows(cursor, sql: str, limit: int, params: dict | None = None) -> Table`. When `params` is `None`, calls `cursor.execute(sql)` (backward compatible); otherwise `cursor.execute(sql, params)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`. Also update the module's `FakeCursor.execute` to accept params:

```python
# In tests/test_db.py, replace FakeCursor.execute signature:
    def execute(self, sql, params=None):
        self.executed = sql
        self.params = params
```

```python
# New test appended to tests/test_db.py
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
```

- [ ] **Step 2: Run tests to verify the new test fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `fetch_rows()` got an unexpected keyword argument `params`.

- [ ] **Step 3: Update the implementation**

Replace the body of `fetch_rows` in `src/oracle_rule_fetcher/db.py`:

```python
def fetch_rows(cursor, sql: str, limit: int, params: dict | None = None) -> Table:
    if params is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, params)
    rows = cursor.fetchmany(limit)
    columns = [desc[0] for desc in cursor.description]
    return Table(columns=columns, rows=[list(row) for row in rows])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (existing and new tests).

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/db.py tests/test_db.py
git commit -m "feat: support bind parameters in fetch_rows

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 4: Pipeline — build a table from CSV records

**Files:**
- Modify: `src/oracle_rule_fetcher/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `fetch_rows` (Task 3), `CsvRecord` + `input_column_names` (Task 2), `InputEntry` (Task 1), `RuleConfig`, `effective_limit`, `Table`.
- Produces: `build_rule_table_from_csv(cursor, rule: RuleConfig, entry: InputEntry, records: list[CsvRecord], global_limit: int, timestamp: str) -> tuple[Table, bool]`. Output columns are `input_column_names(entry) + mapped_result_columns + ["fetched_at", "error"]`. Returns `(table, had_errors)`. Result columns come from the first successful execution; a failed record yields a row with empty result columns and `error = f"Skipped-{exc}"`.

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/test_pipeline.py
from oracle_rule_fetcher.input_config import InputEntry
from oracle_rule_fetcher.csv_source import CsvRecord
from oracle_rule_fetcher.pipeline import build_rule_table_from_csv


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_rule_table_from_csv'`.

- [ ] **Step 3: Write the implementation**

Replace the whole file `src/oracle_rule_fetcher/pipeline.py` with the following (keeps the existing `build_rule_table` unchanged and adds `build_rule_table_from_csv`):

```python
from oracle_rule_fetcher.config import RuleConfig
from oracle_rule_fetcher.csv_source import CsvRecord, input_column_names
from oracle_rule_fetcher.db import fetch_rows
from oracle_rule_fetcher.input_config import InputEntry
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


def build_rule_table_from_csv(
    cursor,
    rule: RuleConfig,
    entry: InputEntry,
    records: list[CsvRecord],
    global_limit: int,
    timestamp: str,
) -> tuple[Table, bool]:
    limit = effective_limit(rule, global_limit)
    input_headers = input_column_names(entry)

    result_columns: list[str] | None = None
    staged: list[tuple[list, list | None, str]] = []
    had_errors = False

    for record in records:
        try:
            result = fetch_rows(cursor, rule.sql, limit, record.binds)
            if result_columns is None:
                result_columns = result.columns
            if result.rows:
                for row in result.rows:
                    staged.append((record.input_values, row, ""))
            else:
                staged.append((record.input_values, None, ""))
        except Exception as exc:  # isolate a single record's query failure
            had_errors = True
            staged.append((record.input_values, None, f"Skipped-{exc}"))

    mapped_columns = [
        rule.column_mapping.get(col, col) for col in (result_columns or [])
    ]
    n_result = len(mapped_columns)
    columns = input_headers + mapped_columns + ["fetched_at", "error"]

    rows: list[list] = []
    for input_values, result_row, error in staged:
        result_part = list(result_row) if result_row is not None else [""] * n_result
        rows.append(list(input_values) + result_part + [timestamp, error])

    return Table(columns=columns, rows=rows), had_errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (existing `build_rule_table` tests and the new CSV tests).

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/pipeline.py tests/test_pipeline.py
git commit -m "feat: build output table from CSV records with error rows

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 5: CLI — wire input config, validation, and mode selection

**Files:**
- Modify: `src/oracle_rule_fetcher/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_input_config`, `validate_input_config` (Task 1); `load_csv_records` (Task 2); `build_rule_table_from_csv` (Task 4); existing `build_rule_table`, `select_enabled`, `write_csv`, `render_table`, `ConfigError`.
- Produces: `parse_args` gains `--input-config` (default `config/input_config.yaml`). `run(..., input_config_path=None, ...)` loads and validates input config, then selects CSV mode vs. normal mode per enabled rule.

- [ ] **Step 1: Write the failing tests**

Update the module `FakeCursor.execute` in `tests/test_cli.py` to accept params, and add a CSV-driven cursor plus new tests:

```python
# Replace FakeCursor.execute in tests/test_cli.py:
    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params
```

```python
# Appended to tests/test_cli.py
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
```

Add `import pytest` at the top of `tests/test_cli.py` if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `run()` got an unexpected keyword argument `input_config_path` and `args.input_config` missing.

- [ ] **Step 3: Update the implementation**

Replace `src/oracle_rule_fetcher/cli.py` with:

```python
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
```

- [ ] **Step 4: Run the full suite to verify nothing regressed**

Run: `uv run pytest -v`
Expected: PASS (all tests across all files).

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/cli.py tests/test_cli.py
git commit -m "feat: select CSV-driven mode per rule with fail-fast validation

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 6: Sample files, sample validation test, and README

**Files:**
- Modify: `config/rules.yaml`
- Create: `config/rules/rsb_sip.yaml`
- Create: `config/input_config.yaml`
- Create: `input/rsb/alm_apo.csv`
- Modify: `README.md`
- Test: `tests/test_input_config.py` (add a sample-validation test)

**Interfaces:**
- Consumes: `load_input_config`, `validate_input_config`, `load_parent_config`.
- Produces: shipped sample config + data files that parse and validate.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_input_config.py`:

```python
def test_sample_input_config_validates():
    from oracle_rule_fetcher.config import load_parent_config

    root = Path(__file__).parent.parent
    parent = load_parent_config(root / "config" / "rules.yaml")
    cfg = load_input_config(root / "config" / "input_config.yaml")
    assert "rsb_sip" in cfg.inputs
    entry = cfg.inputs["rsb_sip"]
    assert entry.query_parameters == {1: "sip_id", 2: "region"}
    validate_input_config(cfg, parent, root / "config")  # no raise
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_input_config.py::test_sample_input_config_validates -v`
Expected: FAIL — `rsb_sip` not yet in the sample config / files missing.

- [ ] **Step 3: Create the sample files**

Replace `config/rules.yaml` with:

```yaml
# Parent configuration: global settings and the rule registry.
global_limit: 100

rules:
  - name: active_customers
    enabled: true
    config: rules/active_customers.yaml
  - name: rsb_sip
    enabled: true
    config: rules/rsb_sip.yaml
```

Create `config/rules/rsb_sip.yaml`:

```yaml
# CSV-driven rule: SQL uses named binds populated per input CSV record.
sql: |
  SELECT ACCOUNT_ID, BALANCE
  FROM ACCOUNTS
  WHERE SIP_ID = :sip_id AND REGION = :region
column_mapping:
  ACCOUNT_ID: account_id
  BALANCE: balance
```

Create `config/input_config.yaml`:

```yaml
# CSV input configuration. Each key must match a rule name in rules.yaml and
# a file under config/rules/<key>.yaml.
inputs:
  rsb_sip:
    file: input/rsb/alm_apo.csv
    column_headers_exist: false      # top row is data; reference columns by 1-based number
    filter_columns:                  # keep only rows whose 3rd column equals "APO"
      - column: 3
        operator: eq
        value: "APO"
    query_parameters:                # CSV column (number) -> SQL reference variable
      1: sip_id
      2: region
```

Create `input/rsb/alm_apo.csv` (no header row):

```
1001,EMEA,APO
1002,APAC,ALM
1003,AMER,APO
1004,EMEA,APO
```

- [ ] **Step 4: Run the sample and full test suite**

Run: `uv run pytest tests/test_input_config.py tests/test_config.py -v`
Expected: PASS (sample validation plus existing config sample test still valid).

Then run the whole suite:

Run: `uv run pytest -v`
Expected: PASS (all tests).

- [ ] **Step 5: Update the README**

Add a section to `README.md` after the "Configuration" section documenting CSV mode:

```markdown
## CSV-driven rules (optional)

A rule can be driven by an input CSV file instead of running its SQL once.
Add an entry to `config/input_config.yaml` keyed by the rule name:

- `file`: path to the input CSV (relative to the working directory).
- `column_headers_exist`: `true` = first row is a header of column names;
  `false` = first row is data (reference columns by 1-based number).
- `filter_columns` (optional): conditions ANDed together; each has `column`
  (1-based number or header name), `operator`
  (`eq`, `ne`, `in`, `gt`, `lt`, `gte`, `lte`), and `value` (`in` takes a list).
- `query_parameters`: maps a CSV column (number or header name) to the SQL
  reference variable used as a named bind (`:name`) in the rule's `sql`.

Each surviving CSV record runs the rule SQL once with its values bound. The
output CSV aggregates all records and adds the mapped input columns, the mapped
result columns, `fetched_at`, and an `error` column (`Skipped-<details>` for a
record whose query failed). Keys in `input_config.yaml` must match both a rule
in `config/rules.yaml` and a `config/rules/<key>.yaml` file, or the run aborts.

Rules without an `input_config.yaml` entry keep the default single-query
behavior. Pass a custom path with `--input-config`.
```

- [ ] **Step 6: Commit**

```bash
git add config/rules.yaml config/rules/rsb_sip.yaml config/input_config.yaml input/rsb/alm_apo.csv README.md tests/test_input_config.py
git commit -m "feat: add CSV-driven sample config, data, and docs

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Final verification

- [ ] Run the full suite: `uv run pytest -v` — expect all tests passing.
- [ ] Confirm no placeholder text remains in shipped files.
```
