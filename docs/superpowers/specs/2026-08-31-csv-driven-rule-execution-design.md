# CSV-Driven Rule Execution Design

## Overview

Add an optional **CSV input mode** to the Oracle Rule Fetcher. Today every
enabled rule runs its SQL once and writes all returned rows. This feature lets a
rule instead be driven by an input CSV file: the CSV is read, its rows are
optionally filtered, and the rule's SQL is executed **once per surviving
record** with values from that record bound as named parameters. Each record's
mapped input values and query results are appended into the rule's single output
CSV.

A new config file `config/input_config.yaml` maps a rule name to its CSV file
and the filtering / parameter-binding details. Rules without a matching entry in
`input_config.yaml` keep the current behavior unchanged.

## Goals

- Drive selected rules from an input CSV file whose path comes from config.
- Filter CSV rows by column number or column name, on one or more columns, with
  multiple operators; support the "no filtering" case.
- Support CSVs that either do or do not have a header row, controlled by a flag.
- Map CSV column values into the rule's SQL via named bind parameters.
- Validate, before any database work, that every `input_config.yaml` key matches
  both a `rules.yaml` entry and a `config/rules/<key>.yaml` file; fail fast on
  mismatch.
- Preserve existing behavior (including output column mapping) for rules with no
  input-config entry.
- Record skipped records in the output with an error column, rather than
  silently dropping them.

## Non-goals

- No change to how the Oracle connection is established or credentialed.
- No new output format; output stays CSV, one file per rule.
- No cross-record joins or aggregation — each record maps to one SQL execution.

## Configuration model

### New file: `config/input_config.yaml`

Top-level `inputs`, keyed by rule name (the "key", e.g. `rsb_sip`):

```yaml
inputs:
  rsb_sip:
    file: input/rsb/alm_apo.csv
    column_headers_exist: false      # false = top row is data; true = top row is header names
    filter_columns:                  # optional; omit or leave empty for no filtering
      - column: 3                    # by number (1-based) OR by header name (needs headers)
        operator: eq                 # eq | ne | in | gt | lt | gte | lte
        value: "APO"
      - column: 5
        operator: in
        value: ["A", "B"]
    query_parameters:                # CSV column (number or name) -> SQL reference variable
      1: sip_id                       # column 1 in the CSV binds to :sip_id in the rule SQL
      2: region                       # column 2 in the CSV binds to :region
```

Field semantics:

- `file` (required): path to the input CSV, resolved relative to the current
  working directory.
- `column_headers_exist` (required): when `true`, the first CSV row supplies
  header names (usable in `filter_columns` and `query_parameters`) and is not
  treated as data; when `false`, the first row is data and columns are
  referenced only by number.
- `filter_columns` (optional): list of conditions ANDed together. Each has:
  - `column`: 1-based integer position, or a header name (only when headers
    exist).
  - `operator`: one of `eq`, `ne`, `in`, `gt`, `lt`, `gte`, `lte`.
  - `value`: scalar for all operators except `in`, which takes a list.
- `query_parameters` (optional but expected in CSV mode): maps each **CSV
  column** (the key: a 1-based number, or a header name when headers exist) to
  the **SQL reference variable** (the value: the bind name used in the rule
  `sql`, without the leading colon). For example `1: sip_id` binds CSV column 1
  to `:sip_id`; `cust_id: customer_id` binds the CSV column named `cust_id` to
  `:customer_id`. The CSV side may be a number or a name; the SQL side is always
  a reference variable.

### Rule file uses named binds

The referenced `config/rules/<key>.yaml` is a normal rule file whose `sql` uses
named bind parameters matching the **values** in `query_parameters` (the SQL
reference variables):

```yaml
sql: |
  SELECT ACCOUNT_ID, BALANCE FROM ACCOUNTS
  WHERE SIP_ID = :sip_id AND REGION = :region
column_mapping:
  ACCOUNT_ID: account_id
  BALANCE: balance
```

### Column reference rules

- Numeric references are **1-based** (first column = 1). This applies to the
  `column` in `filter_columns` and to the CSV-side key in `query_parameters`.
- Name references (header name in `filter_columns.column` or in the
  `query_parameters` key) are allowed only when `column_headers_exist: true`;
  using a name with no headers is a config error.
- A reference (number out of range, or unknown name) is a config/validation
  error surfaced with the rule key.

### Filter operator semantics

- `eq` / `ne`: string equality / inequality against `value`.
- `in`: membership; row kept if the cell equals any element of the `value` list.
- `gt` / `lt` / `gte` / `lte`: numeric comparison when both the cell and `value`
  parse as numbers; otherwise lexicographic string comparison.
- Multiple conditions are ANDed. Empty or omitted `filter_columns` means keep
  all rows.

## Components

New modules:

- `input_config.py`: `load_input_config(path) -> InputConfig`. Parses and
  validates structure into dataclasses (`InputConfig` wrapping a dict of
  `InputEntry` with `file`, `column_headers_exist`, `filter_columns`,
  `query_parameters`). Missing file returns an empty `InputConfig` (CSV mode is
  optional); malformed content raises `ConfigError`.
- `csv_source.py`: reads a CSV honoring `column_headers_exist`, resolves column
  references (the CSV-side keys of `filter_columns.column` and
  `query_parameters`), applies `filter_columns`, and yields per-record
  bind-parameter dicts keyed by the SQL reference variable
  (`{reference_variable: value}`). Also exposes each record's mapped input values
  for the output row and error reporting.

Changed modules:

- `db.py`: `fetch_rows(cursor, sql, limit, params=None)` passes binds to
  `cursor.execute` (call unchanged when `params` is `None`).
- `pipeline.py`: add `build_rule_table_from_csv(cursor, rule, entry, global_limit,
  timestamp)` that iterates records, executes SQL per record, prepends the mapped
  input columns to each result row, applies the existing `column_mapping` to the
  result columns, and appends `fetched_at` plus an `error` column. Existing
  `build_rule_table` is untouched.
- `cli.py`: add `--input-config` (default `config/input_config.yaml`). Load it,
  run startup validation, then for each enabled rule choose CSV mode vs. normal
  mode by presence of a matching input entry.

## Startup validation (fail fast)

After loading `rules.yaml` and `input_config.yaml`, and **before** opening any
database connection, for every key in `input_config.yaml`:

1. It must match the `name` of a rule in `rules.yaml`.
2. A `config/rules/<key>.yaml` file must exist (the rule's `config` path).

Any mismatch raises a clear error naming the offending key and aborts the whole
run before DB work. (Rules present in `rules.yaml` but absent from
`input_config.yaml` are valid — they run in normal mode.)

## Output behavior

In CSV mode the query is executed once per surviving CSV record, and the rule's
single output CSV aggregates the results of **all** iterations. Each record
normally contributes **one output line**. In this order, every line contains:
the **mapped CSV input columns** (the values bound into the query), the **mapped
query-result columns**, the existing `fetched_at` timestamp column, and a
trailing `error` column.

- Input columns are the `query_parameters` entries, headed by their SQL
  reference variables (e.g. `sip_id`, `region`). Because they come straight from
  the CSV record, they are always present and filled — even for skipped records.
- Successful record (query returns one row): input columns filled, result
  columns filled, `error` empty — one output line.
- Record whose query returns multiple rows: one output line per returned row,
  each repeating that record's input columns.
- Record whose query returns no rows: one output line with input columns filled
  and result columns empty (`error` empty).
- Skipped record (its query raised): one output line with input columns filled,
  result columns empty, and `error` set to `Skipped-<details>`, where
  `<details>` includes the exception message (e.g.
  `Skipped-ORA-00942: table or view does not exist`). The input columns already
  identify which record failed.

The input-column set is fixed and known upfront from `query_parameters`. The
result-column set is established from the **first successful** execution
(`cursor.description`); skipped rows seen before that are buffered and filled
once the result columns are known. If **no** record succeeds, the output carries
the input columns plus `fetched_at` and `error` (no result columns), one row per
record.

Normal-mode rules (no input entry) are unchanged: no input or `error` columns,
one query, all rows.

## Limits and error handling

- `limit` / `global_limit` continues to bound `fetchmany` per query execution
  (now per record in CSV mode).
- A missing CSV file for a rule is logged with rule context; that rule is
  skipped and the run exits non-zero (consistent with current per-rule
  isolation).
- Individual record query failures are captured as `Skipped-...` output rows
  (not fatal) and also logged; the run still exits non-zero to signal that
  errors occurred.
- Config/validation errors (mismatched keys, bad column references, malformed
  YAML) remain run-level and abort before DB work.

## Sample files shipped

- `config/input_config.yaml` — with the `rsb_sip` entry above.
- `config/rules/rsb_sip.yaml` — bind-parameter SQL + `column_mapping`.
- A `rsb_sip` entry added to `config/rules.yaml`.
- `input/rsb/alm_apo.csv` — sample data with **no** header row, demonstrating
  `column_headers_exist: false`.

## Testing

- `input_config.py`: valid parse; missing file yields empty config; malformed
  structure raises `ConfigError`; name reference without headers is rejected.
- `csv_source.py`: read with and without headers; column reference by number
  (1-based) and by name; `query_parameters` maps CSV column (key) to SQL
  reference variable (value) — verify by number and by name; each operator
  (`eq`, `ne`, `in`, `gt`, `lt`, `gte`, `lte`); numeric vs. string comparison;
  no-filter case keeps all rows; per-record bind dict keyed by reference
  variable.
- `db.py`: `fetch_rows` forwards bind params to `cursor.execute`.
- `pipeline.py`: per-record execution aggregates all iterations into one table;
  input columns prepended and result columns mapped; one output line per record
  in the common single-row case; a record returning multiple rows yields one
  line per row (input columns repeated); a record returning no rows yields one
  line with empty result columns; `fetched_at` and `error` columns present; a
  failing record produces a `Skipped-...` row (with its input columns filled)
  while others succeed; all-fail case yields input + error rows with no result
  columns.
- Startup validation: mismatched key (missing rule entry, or missing rule file)
  aborts before DB work with the key named.
- `cli.py`: end-to-end CSV-mode run writes the expected combined output; a rule
  with no input entry still runs in normal mode; missing `input_config.yaml`
  leaves all rules in normal mode.
- Sample `config/input_config.yaml` validates and its keys resolve.

## Conventions

- Follow existing module boundaries, dataclass-based config, and `ConfigError`
  usage.
- Keep business logic out of `cli.py`.
- Reference CSV columns as 1-based numbers throughout.
