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

## Instrument Search

Reads a CSV file's `instrument` column, looks up each instrument on
[MarketScreener NL](https://nl.marketscreener.com/), extracts the current
price, and writes it back to the CSV in a `Web_Price` column. A screenshot
is saved for each instrument found.

### Setup (one-time)

```bash
uv run playwright install chromium
```

### Usage

```bash
uv run instrument-search --csv data/orders-onhold.csv
uv run instrument-search --csv data/orders-onhold.csv --screenshots-dir my_screenshots
```

Screenshots are saved to `screenshots/<csv_stem>/<csv_stem>-<instrument>-<row>.png`
by default.
