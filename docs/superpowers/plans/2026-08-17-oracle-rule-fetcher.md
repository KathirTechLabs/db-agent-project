# Oracle Rule Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `uv`-managed Python CLI that fetches Oracle data per configurable rule, maps columns to functional names, prints a table, and writes timestamped CSV plus a log file.

**Architecture:** A small `src/` package with focused modules — config loading, rule selection, Oracle access, a per-rule transform pipeline, table rendering, CSV export, and logging. A parent YAML config registers rules (name + enabled) and the global limit; each rule has its own YAML file with its query, optional limit, and column mapping. Database credentials come from environment variables.

**Tech Stack:** Python 3.11+, `uv`, `oracledb` (thin mode), `PyYAML`, `tabulate`, `pytest`.

## Global Constraints

- Python requirement: `>=3.11`
- Dependency floors: `oracledb>=2.0`, `PyYAML>=6.0`, `tabulate>=0.9`; dev: `pytest>=8.0`
- Dependency management and execution go through `uv` (`uv sync`, `uv run ...`)
- Package name: `oracle_rule_fetcher` under `src/` layout
- Database credentials come only from environment variables: `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN` (never from config files)
- Added CSV timestamp column name: `fetched_at`
- Per-rule CSV output file name: `<rule_name>.csv`
- Row limits apply per rule via `cursor.fetchmany(limit)`; per-rule `limit` overrides `global_limit`

---

## File Structure

```
db-agent-project/
├── pyproject.toml                       # uv project + deps + entry point
├── .gitignore
├── .env.example                         # documents DB env vars
├── config/
│   ├── rules.yaml                       # sample parent config (registry + global_limit)
│   └── rules/
│       └── active_customers.yaml        # sample individual rule config
├── src/oracle_rule_fetcher/
│   ├── __init__.py
│   ├── models.py                        # Table dataclass (shared data structure)
│   ├── config.py                        # dataclasses + YAML loaders
│   ├── rules.py                         # select_enabled, effective_limit
│   ├── db.py                            # DbSettings, load_db_settings, OracleClient, fetch_rows
│   ├── transform.py                     # apply_column_mapping, add_timestamp_column
│   ├── render.py                        # render_table
│   ├── export.py                        # write_csv
│   ├── app_logging.py                   # configure_logging
│   ├── pipeline.py                      # build_rule_table (per-rule transform pipeline)
│   └── cli.py                           # main + arg parsing + orchestration
└── tests/
    ├── test_models.py
    ├── test_config.py
    ├── test_rules.py
    ├── test_db.py
    ├── test_transform.py
    ├── test_render.py
    ├── test_export.py
    ├── test_app_logging.py
    ├── test_pipeline.py
    └── test_cli.py
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/oracle_rule_fetcher/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing
- Produces: importable package `oracle_rule_fetcher` with `__version__: str`; `uv run pytest` works

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "oracle-rule-fetcher"
version = "0.1.0"
description = "Fetch Oracle data based on configurable rules"
requires-python = ">=3.11"
dependencies = [
    "oracledb>=2.0",
    "PyYAML>=6.0",
    "tabulate>=0.9",
]

[project.scripts]
oracle-rule-fetcher = "oracle_rule_fetcher.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/oracle_rule_fetcher"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
.env
*.log
output/
.pytest_cache/
*.egg-info/
```

- [ ] **Step 3: Create `.env.example`**

```dotenv
# Oracle database connection (thin mode)
ORACLE_USER=my_user
ORACLE_PASSWORD=my_password
# DSN format: host:port/service_name
ORACLE_DSN=localhost:1521/XEPDB1
```

- [ ] **Step 4: Create `src/oracle_rule_fetcher/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Write the smoke test**

```python
# tests/test_smoke.py
import oracle_rule_fetcher


def test_package_has_version():
    assert oracle_rule_fetcher.__version__ == "0.1.0"
```

- [ ] **Step 6: Sync and run the test**

Run: `uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS (uv creates the environment, installs deps, test passes)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .env.example src/oracle_rule_fetcher/__init__.py tests/test_smoke.py uv.lock
git commit -m "chore: scaffold uv project for oracle rule fetcher"
```

---

## Task 2: Shared Table model

**Files:**
- Create: `src/oracle_rule_fetcher/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Table` dataclass with fields `columns: list[str]` and `rows: list[list]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from oracle_rule_fetcher.models import Table


def test_table_holds_columns_and_rows():
    table = Table(columns=["ID", "NAME"], rows=[[1, "Alice"], [2, "Bob"]])
    assert table.columns == ["ID", "NAME"]
    assert table.rows == [[1, "Alice"], [2, "Bob"]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/models.py
from dataclasses import dataclass, field


@dataclass
class Table:
    columns: list[str]
    rows: list[list] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/models.py tests/test_models.py
git commit -m "feat: add shared Table data model"
```

---

## Task 3: Config loaders and sample config files

**Files:**
- Create: `src/oracle_rule_fetcher/config.py`
- Create: `config/rules.yaml`
- Create: `config/rules/active_customers.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `RuleRegistryEntry(name: str, enabled: bool, config: str)`
  - `ParentConfig(global_limit: int, rules: list[RuleRegistryEntry])`
  - `RuleConfig(name: str, sql: str, limit: int | None, column_mapping: dict[str, str])`
  - `ConfigError(Exception)`
  - `load_parent_config(path: str | Path) -> ParentConfig`
  - `load_rule_config(path: str | Path, name: str) -> RuleConfig`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
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
    parent = load_parent_config("config/rules.yaml")
    assert parent.global_limit >= 1
    assert any(r.name == "active_customers" for r in parent.rules)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.config'`

- [ ] **Step 3: Write the config module**

```python
# src/oracle_rule_fetcher/config.py
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    """Raised when a config file is missing or malformed."""


@dataclass
class RuleRegistryEntry:
    name: str
    enabled: bool
    config: str


@dataclass
class ParentConfig:
    global_limit: int
    rules: list[RuleRegistryEntry]


@dataclass
class RuleConfig:
    name: str
    sql: str
    limit: int | None = None
    column_mapping: dict[str, str] = field(default_factory=dict)


def load_parent_config(path: str | Path) -> ParentConfig:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ConfigError(f"Parent config {path} must be a mapping")
    if "global_limit" not in data:
        raise ConfigError(f"Parent config {path} missing 'global_limit'")

    rules: list[RuleRegistryEntry] = []
    for entry in data.get("rules", []) or []:
        for key in ("name", "enabled", "config"):
            if key not in entry:
                raise ConfigError(f"Rule entry {entry!r} missing '{key}'")
        rules.append(
            RuleRegistryEntry(
                name=entry["name"],
                enabled=bool(entry["enabled"]),
                config=entry["config"],
            )
        )
    return ParentConfig(global_limit=int(data["global_limit"]), rules=rules)


def load_rule_config(path: str | Path, name: str) -> RuleConfig:
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ConfigError(f"Rule config {path} must be a mapping")
    if "sql" not in data:
        raise ConfigError(f"Rule config {path} missing 'sql'")

    limit = data.get("limit")
    return RuleConfig(
        name=name,
        sql=data["sql"],
        limit=None if limit is None else int(limit),
        column_mapping=data.get("column_mapping") or {},
    )
```

- [ ] **Step 4: Create the sample parent config**

```yaml
# config/rules.yaml
# Parent configuration: global settings and the rule registry.
global_limit: 100

rules:
  - name: active_customers
    enabled: true
    config: rules/active_customers.yaml
```

- [ ] **Step 5: Create the sample rule config**

```yaml
# config/rules/active_customers.yaml
# Individual rule configuration: query, optional limit, and column mapping.
sql: >
  SELECT CUST_ID, CUST_NAME, SIGNUP_DATE
  FROM CUSTOMERS
  WHERE STATUS = 'ACTIVE'
limit: 25
column_mapping:
  CUST_ID: customer_id
  CUST_NAME: customer_name
  SIGNUP_DATE: signup_date
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (all seven tests, including `test_sample_parent_config_is_valid`)

- [ ] **Step 7: Commit**

```bash
git add src/oracle_rule_fetcher/config.py config/rules.yaml config/rules/active_customers.yaml tests/test_config.py
git commit -m "feat: add config loaders and sample config files"
```

---

## Task 4: Rule selection and limit resolution

**Files:**
- Create: `src/oracle_rule_fetcher/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: `ParentConfig`, `RuleRegistryEntry`, `RuleConfig` from `config`
- Produces:
  - `select_enabled(parent: ParentConfig) -> list[RuleRegistryEntry]`
  - `effective_limit(rule: RuleConfig, global_limit: int) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rules.py
from oracle_rule_fetcher.config import ParentConfig, RuleConfig, RuleRegistryEntry
from oracle_rule_fetcher.rules import effective_limit, select_enabled


def test_select_enabled_filters_disabled():
    parent = ParentConfig(
        global_limit=50,
        rules=[
            RuleRegistryEntry("a", True, "a.yaml"),
            RuleRegistryEntry("b", False, "b.yaml"),
            RuleRegistryEntry("c", True, "c.yaml"),
        ],
    )
    assert [r.name for r in select_enabled(parent)] == ["a", "c"]


def test_effective_limit_uses_rule_limit_when_set():
    rule = RuleConfig(name="a", sql="SELECT 1 FROM DUAL", limit=10)
    assert effective_limit(rule, global_limit=50) == 10


def test_effective_limit_falls_back_to_global():
    rule = RuleConfig(name="a", sql="SELECT 1 FROM DUAL", limit=None)
    assert effective_limit(rule, global_limit=50) == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.rules'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/rules.py
from oracle_rule_fetcher.config import ParentConfig, RuleConfig, RuleRegistryEntry


def select_enabled(parent: ParentConfig) -> list[RuleRegistryEntry]:
    return [rule for rule in parent.rules if rule.enabled]


def effective_limit(rule: RuleConfig, global_limit: int) -> int:
    return rule.limit if rule.limit is not None else global_limit
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/rules.py tests/test_rules.py
git commit -m "feat: add rule selection and limit resolution"
```

---

## Task 5: Database settings and row fetching

**Files:**
- Create: `src/oracle_rule_fetcher/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Table` from `models`
- Produces:
  - `DbSettings(user: str, password: str, dsn: str)`
  - `MissingEnvVarError(Exception)`
  - `load_db_settings(env: Mapping[str, str]) -> DbSettings`
  - `OracleClient(settings: DbSettings)` with `.cursor()` (connects lazily) and `.close()`
  - `fetch_rows(cursor, sql: str, limit: int) -> Table` (executes SQL, returns at most `limit` rows via `fetchmany`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db.py
import pytest

from oracle_rule_fetcher.db import (
    DbSettings,
    MissingEnvVarError,
    fetch_rows,
    load_db_settings,
)


class FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows
        self.executed = None

    def execute(self, sql):
        self.executed = sql

    def fetchmany(self, size):
        return self._rows[:size]


def test_load_db_settings_reads_env():
    env = {
        "ORACLE_USER": "scott",
        "ORACLE_PASSWORD": "tiger",
        "ORACLE_DSN": "localhost:1521/XEPDB1",
    }
    settings = load_db_settings(env)
    assert settings == DbSettings("scott", "tiger", "localhost:1521/XEPDB1")


def test_load_db_settings_missing_var_raises():
    env = {"ORACLE_USER": "scott", "ORACLE_PASSWORD": "tiger"}
    with pytest.raises(MissingEnvVarError, match="ORACLE_DSN"):
        load_db_settings(env)


def test_load_db_settings_empty_var_raises():
    env = {"ORACLE_USER": "", "ORACLE_PASSWORD": "tiger", "ORACLE_DSN": "d"}
    with pytest.raises(MissingEnvVarError, match="ORACLE_USER"):
        load_db_settings(env)


def test_fetch_rows_returns_table_with_columns_and_rows():
    cursor = FakeCursor(
        description=[("CUST_ID",), ("CUST_NAME",)],
        rows=[(1, "Alice"), (2, "Bob"), (3, "Carol")],
    )
    table = fetch_rows(cursor, "SELECT CUST_ID, CUST_NAME FROM CUSTOMERS", limit=2)
    assert cursor.executed == "SELECT CUST_ID, CUST_NAME FROM CUSTOMERS"
    assert table.columns == ["CUST_ID", "CUST_NAME"]
    assert table.rows == [[1, "Alice"], [2, "Bob"]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.db'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/db.py
from collections.abc import Mapping
from dataclasses import dataclass

import oracledb

from oracle_rule_fetcher.models import Table

REQUIRED_ENV = ("ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_DSN")


class MissingEnvVarError(Exception):
    """Raised when a required database environment variable is missing."""


@dataclass
class DbSettings:
    user: str
    password: str
    dsn: str


def load_db_settings(env: Mapping[str, str]) -> DbSettings:
    missing = [key for key in REQUIRED_ENV if not env.get(key)]
    if missing:
        raise MissingEnvVarError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    return DbSettings(
        user=env["ORACLE_USER"],
        password=env["ORACLE_PASSWORD"],
        dsn=env["ORACLE_DSN"],
    )


class OracleClient:
    def __init__(self, settings: DbSettings):
        self.settings = settings
        self._conn = None

    def connect(self):
        self._conn = oracledb.connect(
            user=self.settings.user,
            password=self.settings.password,
            dsn=self.settings.dsn,
        )

    def cursor(self):
        if self._conn is None:
            self.connect()
        return self._conn.cursor()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def fetch_rows(cursor, sql: str, limit: int) -> Table:
    cursor.execute(sql)
    rows = cursor.fetchmany(limit)
    columns = [desc[0] for desc in cursor.description]
    return Table(columns=columns, rows=[list(row) for row in rows])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (`OracleClient.connect` is not exercised — no live DB needed)

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/db.py tests/test_db.py
git commit -m "feat: add db settings loader and row fetching"
```

---

## Task 6: Column mapping and timestamp transform

**Files:**
- Create: `src/oracle_rule_fetcher/transform.py`
- Test: `tests/test_transform.py`

**Interfaces:**
- Consumes: `Table` from `models`
- Produces:
  - `apply_column_mapping(table: Table, mapping: dict[str, str]) -> Table` (renames mapped columns; unmapped kept as-is)
  - `add_timestamp_column(table: Table, timestamp: str, column_name: str = "fetched_at") -> Table` (appends a timestamp value to every row)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transform.py
from oracle_rule_fetcher.models import Table
from oracle_rule_fetcher.transform import add_timestamp_column, apply_column_mapping


def test_apply_column_mapping_renames_mapped_columns():
    table = Table(columns=["CUST_ID", "CUST_NAME"], rows=[[1, "Alice"]])
    result = apply_column_mapping(table, {"CUST_ID": "customer_id", "CUST_NAME": "customer_name"})
    assert result.columns == ["customer_id", "customer_name"]
    assert result.rows == [[1, "Alice"]]


def test_apply_column_mapping_keeps_unmapped_columns():
    table = Table(columns=["CUST_ID", "EXTRA"], rows=[[1, "x"]])
    result = apply_column_mapping(table, {"CUST_ID": "customer_id"})
    assert result.columns == ["customer_id", "EXTRA"]


def test_add_timestamp_column_appends_value_to_every_row():
    table = Table(columns=["customer_id"], rows=[[1], [2]])
    result = add_timestamp_column(table, "2026-08-17T14:30:00", column_name="fetched_at")
    assert result.columns == ["customer_id", "fetched_at"]
    assert result.rows == [[1, "2026-08-17T14:30:00"], [2, "2026-08-17T14:30:00"]]


def test_add_timestamp_column_default_name():
    table = Table(columns=["a"], rows=[[1]])
    result = add_timestamp_column(table, "T")
    assert result.columns == ["a", "fetched_at"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transform.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.transform'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/transform.py
from oracle_rule_fetcher.models import Table


def apply_column_mapping(table: Table, mapping: dict[str, str]) -> Table:
    columns = [mapping.get(name, name) for name in table.columns]
    return Table(columns=columns, rows=[list(row) for row in table.rows])


def add_timestamp_column(
    table: Table, timestamp: str, column_name: str = "fetched_at"
) -> Table:
    columns = table.columns + [column_name]
    rows = [list(row) + [timestamp] for row in table.rows]
    return Table(columns=columns, rows=rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_transform.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/transform.py tests/test_transform.py
git commit -m "feat: add column mapping and timestamp transforms"
```

---

## Task 7: Terminal table rendering

**Files:**
- Create: `src/oracle_rule_fetcher/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Table` from `models`
- Produces: `render_table(table: Table) -> str` (a printable grid using `tabulate`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_render.py
from oracle_rule_fetcher.models import Table
from oracle_rule_fetcher.render import render_table


def test_render_table_includes_headers_and_values():
    table = Table(columns=["customer_id", "customer_name"], rows=[[1, "Alice"]])
    output = render_table(table)
    assert "customer_id" in output
    assert "customer_name" in output
    assert "Alice" in output


def test_render_table_empty_rows_still_shows_headers():
    table = Table(columns=["customer_id"], rows=[])
    output = render_table(table)
    assert "customer_id" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.render'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/render.py
from tabulate import tabulate

from oracle_rule_fetcher.models import Table


def render_table(table: Table) -> str:
    return tabulate(table.rows, headers=table.columns, tablefmt="grid")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/render.py tests/test_render.py
git commit -m "feat: add terminal table rendering"
```

---

## Task 8: CSV export

**Files:**
- Create: `src/oracle_rule_fetcher/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `Table` from `models`
- Produces: `write_csv(table: Table, path: str | Path) -> None` (writes header row + data rows)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export.py
import csv

from oracle_rule_fetcher.export import write_csv
from oracle_rule_fetcher.models import Table


def test_write_csv_writes_header_and_rows(tmp_path):
    table = Table(
        columns=["customer_id", "fetched_at"],
        rows=[[1, "2026-08-17T14:30:00"], [2, "2026-08-17T14:30:00"]],
    )
    path = tmp_path / "active_customers.csv"
    write_csv(table, path)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["customer_id", "fetched_at"]
    assert rows[1] == ["1", "2026-08-17T14:30:00"]
    assert rows[2] == ["2", "2026-08-17T14:30:00"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.export'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/export.py
import csv
from pathlib import Path

from oracle_rule_fetcher.models import Table


def write_csv(table: Table, path: str | Path) -> None:
    path = Path(path)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(table.columns)
        writer.writerows(table.rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_export.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/export.py tests/test_export.py
git commit -m "feat: add csv export"
```

---

## Task 9: File logging

**Files:**
- Create: `src/oracle_rule_fetcher/app_logging.py`
- Test: `tests/test_app_logging.py`

**Interfaces:**
- Consumes: nothing
- Produces: `configure_logging(log_path: str | Path) -> logging.Logger` (returns a logger named `oracle_rule_fetcher` that writes timestamped lines to `log_path`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_app_logging.py
import re

from oracle_rule_fetcher.app_logging import configure_logging


def test_configure_logging_writes_timestamped_entry(tmp_path):
    log_path = tmp_path / "run.log"
    logger = configure_logging(log_path)
    logger.info("processed rule active_customers")

    for handler in logger.handlers:
        handler.flush()

    content = log_path.read_text()
    assert "processed rule active_customers" in content
    # Line begins with an ISO-like date (YYYY-MM-DD)
    assert re.search(r"\d{4}-\d{2}-\d{2}", content)


def test_configure_logging_does_not_duplicate_handlers(tmp_path):
    log_path = tmp_path / "run.log"
    logger = configure_logging(log_path)
    logger = configure_logging(log_path)
    assert len(logger.handlers) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_app_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.app_logging'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/app_logging.py
import logging
from pathlib import Path

LOGGER_NAME = "oracle_rule_fetcher"


def configure_logging(log_path: str | Path) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.FileHandler(Path(log_path))
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    return logger
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_app_logging.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/app_logging.py tests/test_app_logging.py
git commit -m "feat: add file logging configuration"
```

---

## Task 10: Per-rule transform pipeline

**Files:**
- Create: `src/oracle_rule_fetcher/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `RuleConfig` from `config`; `effective_limit` from `rules`; `fetch_rows` from `db`; `apply_column_mapping`, `add_timestamp_column` from `transform`; `Table` from `models`
- Produces: `build_rule_table(cursor, rule: RuleConfig, global_limit: int, timestamp: str) -> Table` (fetch → limit → map columns → append timestamp)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
from oracle_rule_fetcher.config import RuleConfig
from oracle_rule_fetcher.pipeline import build_rule_table


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/pipeline.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/pipeline.py tests/test_pipeline.py
git commit -m "feat: add per-rule transform pipeline"
```

---

## Task 11: CLI orchestration

**Files:**
- Create: `src/oracle_rule_fetcher/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above — `load_parent_config`, `load_rule_config` from `config`; `select_enabled` from `rules`; `load_db_settings`, `OracleClient` from `db`; `build_rule_table` from `pipeline`; `render_table` from `render`; `write_csv` from `export`; `configure_logging` from `app_logging`
- Produces:
  - `parse_args(argv: list[str] | None) -> argparse.Namespace` with attributes `config: str`, `output_dir: str`, `log_file: str`
  - `run(parent_path, output_dir, log_file, cursor_provider, now=datetime.now) -> int` (orchestrates rules against a caller-supplied cursor provider; testable without a live DB)
  - `main(argv: list[str] | None = None) -> int` (wires argparse + env + `OracleClient` into `run`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rule_fetcher.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/oracle_rule_fetcher/cli.py
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
            table = build_rule_table(
                cursor, rule, parent.global_limit, timestamp
            )
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (both enabled-rule and failing-rule isolation tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS (all tests across every module)

- [ ] **Step 6: Commit**

```bash
git add src/oracle_rule_fetcher/cli.py tests/test_cli.py
git commit -m "feat: add cli orchestration"
```

---

## Task 12: Usage documentation

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the CLI and config layout from earlier tasks
- Produces: usage documentation (no code interface)

- [ ] **Step 1: Write `README.md`**

````markdown
# Oracle Rule Fetcher

A `uv`-managed Python CLI that fetches data from an Oracle database based on
configurable rules, maps columns to functional names, prints a table, and
writes timestamped CSV output plus a log file.

## Setup

```bash
uv sync
cp .env.example .env   # then edit with real credentials
```

Set the database connection via environment variables:

- `ORACLE_USER`
- `ORACLE_PASSWORD`
- `ORACLE_DSN` (e.g. `host:1521/service_name`)

## Configuration

- `config/rules.yaml` — parent config: `global_limit` and the rule registry
  (each rule has `name`, `enabled`, and a `config` path).
- `config/rules/<rule>.yaml` — one file per rule: `sql`, optional `limit`,
  and optional `column_mapping`.

To add a rule: add an entry to `config/rules.yaml` and create its rule file.
To disable a rule: set `enabled: false` in the parent config.

## Usage

```bash
uv run oracle-rule-fetcher --config config/rules.yaml --output-dir output --log-file run.log
```

Each enabled rule writes `output/<rule_name>.csv` (including a `fetched_at`
timestamp column) and appends a timestamped line to the log file.

## Testing

```bash
uv run pytest -v                       # full suite
uv run pytest tests/test_config.py -v  # a single test file
```
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add usage README"
```

---

## Self-Review

**1. Spec coverage:**

| Spec requirement | Task |
|---|---|
| `uv` dependency management + execution | Task 1 |
| Modular `src/` package | Tasks 2–11 |
| Fetch from Oracle by rules | Tasks 5, 10, 11 |
| Unique per-rule query, configurable | Task 3 (rule config `sql`) |
| Add/remove/enable/disable rules | Task 3 (parent registry), Task 4 (`select_enabled`) |
| Global limit + per-rule override | Task 3 (`global_limit`/`limit`), Task 4 (`effective_limit`) |
| Table view output | Task 7 |
| Column names → functional names via config | Task 3 (`column_mapping`), Task 6 (`apply_column_mapping`) |
| CSV output with timestamp column | Task 6 (`add_timestamp_column`), Task 8 (`write_csv`) |
| Log file with timestamp | Task 9 |
| DB config via environment variables | Task 5 (`load_db_settings`), Task 11 (`main`) |
| Sample config files | Task 3 (`config/rules.yaml`, `config/rules/active_customers.yaml`), Task 1 (`.env.example`) |
| Two-tier config (parent + per-rule) | Task 3 loaders, Task 11 resolution |
| Per-rule failure isolation | Task 11 (`run` try/except) |

No gaps found.

**2. Placeholder scan:** No `TBD`/`TODO`/"handle edge cases" placeholders; every code and test step contains concrete content.

**3. Type consistency:** `Table(columns, rows)` used consistently across `models`, `db`, `transform`, `render`, `export`, `pipeline`. `RuleConfig`/`ParentConfig`/`RuleRegistryEntry` field names match between `config`, `rules`, `pipeline`, and `cli`. `build_rule_table(cursor, rule, global_limit, timestamp)` signature matches its call in `cli.run`. `effective_limit(rule, global_limit)` matches usage in `pipeline`.
