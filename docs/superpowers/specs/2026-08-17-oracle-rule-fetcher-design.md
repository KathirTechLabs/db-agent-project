# Oracle Rule Fetcher Design

## Overview

Build a Python CLI project managed with `uv` that fetches data from an Oracle SQL database based on configurable rules.
Each rule has its own SQL query, optional record limit, and enabled flag.
The CLI prints a terminal table, writes each rule's rows to a CSV file, and appends run details to a timestamped log file.

## Goals

- Use `uv` for dependency management and execution.
- Keep the code modular and easy to extend.
- Make rules configurable so they can be added, removed, enabled, or disabled without changing code.
- Support a global record limit plus per-rule overrides.
- Map raw database column names to functional names through YAML configuration.
- Persist output as CSV and log each run with timestamps.

## Architecture

The project will be a small CLI package with clear module boundaries:

- `config`: load and validate the parent config and individual rule config files
- `rules`: represent rule definitions and selection logic
- `db`: Oracle connection (from environment variables) and query execution
- `transform`: rename/map columns and normalize rows
- `render`: print tables in the terminal
- `export`: write CSV output
- `app_logging`: configure file logging

The repository will start with a standard `src/` layout and a `pyproject.toml` for `uv`.

Key runtime dependencies:

- `oracledb`: Oracle database driver (thin mode, no Oracle client install required)
- `PyYAML`: YAML configuration parsing
- `tabulate`: terminal table rendering

## Configuration model

Use YAML for all runtime configuration, split into two tiers.

### Parent configuration file

A single parent config file is the entry point. It holds global settings and
the rule registry:

- `global_limit`: default maximum rows per rule when a rule does not set its own limit
- `rules`: list of registered rules
  - `name`: unique rule identifier
  - `enabled`: whether the rule runs
  - `config`: path to this rule's individual config file

Adding a rule means adding an entry here and creating its rule config file.
Removing or disabling a rule is an edit to this file only.

### Individual rule configuration files

Each rule has its own config file, referenced from the parent. It holds
everything specific to that rule:

- `sql`: the rule's SQL query
- `limit` (optional): per-rule row limit override
- `column_mapping` (optional): map this rule's Oracle column names to functional names

Because every rule is unique and has its own query, its query and column
mapping live in the rule's own file rather than in the parent. A rule with no
`column_mapping` keeps the raw column names returned by its query.

### Limit behavior

- If a rule config defines `limit`, use it.
- Otherwise, use `global_limit` from the parent config.
- Limits apply per rule, not across the full run.

### Database connection

Oracle connection details are supplied through environment variables, not
config files, so credentials stay out of version control:

- `ORACLE_USER`: database username
- `ORACLE_PASSWORD`: database password
- `ORACLE_DSN`: data source name (host, port, and service name)

The application reads these at startup and fails fast with a clear message if
any required variable is missing. A `.env.example` file documents the expected
variables for local setup.

### Sample configuration

The repository ships sample config files for reference and testing:

- a sample parent config registering one or more example rules
- a sample individual rule config with an example query and column mapping
- a `.env.example` documenting the database environment variables

These samples double as fixtures for the config-loading tests.

## Data flow

1. CLI starts and loads the parent config file.
2. The parent config and each enabled rule's config file are validated before any database connection is opened.
3. Database connection settings are read from environment variables and checked for completeness.
4. Enabled rules are collected from the parent registry, and each rule's individual config file is loaded.
5. For each rule:
   - execute the rule SQL against Oracle
   - apply the effective row limit
   - rename columns using the rule's column mapping
   - print a table to the terminal
   - write rows to that rule's CSV file
   - write a timestamped log entry

Each rule writes to its own CSV file (named by rule) because rules have
different columns. Every CSV row includes a timestamp column added by the
application recording when the row was fetched.

## Error handling

- Fail fast on invalid config or missing required config fields.
- Fail fast with a clear message when required database environment variables are missing.
- Surface Oracle connection/query failures clearly with rule context.
- Skip only the failing rule when the error is isolated to one rule; continue processing other enabled rules.
- Treat output path or logging failures as run-level failures because they affect persistence.

## Testing

Planned tests will cover:

- parent config parsing and validation
- individual rule config parsing and validation
- parent-to-rule config resolution (loading referenced rule files)
- rule enable/disable behavior
- global and per-rule limit resolution
- database environment variable validation
- column name mapping
- CSV export formatting
- terminal table rendering

## Initial project conventions

- Use `uv` commands for sync, run, and test workflows.
- Keep business logic out of the CLI entry point.
- Prefer small modules over a large monolith.
- Keep runtime config in YAML rather than hard-coded query definitions.
