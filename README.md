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

## CSV-driven rules (optional)

A rule can be driven by an input CSV file instead of running its SQL once.
Add an entry to `config/input_config.yaml` keyed by the rule name:

- `file`: path to the input CSV (relative to the working directory).
- `column_headers_exist`: `true` = first row is a header of column names;
  `false` = first row is data (reference columns by 1-based number).
- `delimiter` (optional): the field separator for the input file, a single
  character. Defaults to `,`. For example, use `"|"` for pipe-delimited files.
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
