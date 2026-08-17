# Instrument Search Feature Design

**Date:** 2026-08-17  
**Branch:** instrument-search

---

## Overview

A new standalone CLI command `instrument-search` that reads a CSV file, looks up each value in the `instrument` column on [MarketScreener NL](https://nl.marketscreener.com/), selects the first autocomplete suggestion, extracts the current rate/price from the instrument page, and saves a screenshot.

---

## CLI Interface

```bash
instrument-search --csv <path/to/file.csv> [--screenshots-dir screenshots]
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--csv` | Yes | — | Path to the input CSV file |
| `--screenshots-dir` | No | `screenshots` | Root folder for screenshot output |

---

## Architecture

### New files

- `src/oracle_rule_fetcher/instrument_search.py` — all search/scrape logic
- New entry point registered in `pyproject.toml`

Existing code (Oracle pipeline, config, export) is **not touched**.

### Entry point wiring

```toml
[project.scripts]
instrument-search = "oracle_rule_fetcher.instrument_search:main"
```

---

## Flow

The browser (headless Chromium) is launched **once** at the start and reused for
all rows. A **fresh page** is created per row and closed in a `finally` block so a
crashed page never cascades failures to later rows. Every row's `Web_Price` is
initialized to `""` up front, and rows are processed by index so the fetched price
is written to the exact source row (duplicates and failures never shift values).

For each row (by index) in the CSV:

1. Read and strip the `instrument` column value.
   - If blank/whitespace-only → log warning, leave `Web_Price` empty, skip.
2. Navigate to `https://nl.marketscreener.com/` on a fresh page.
3. Type the instrument name into the site's search input.
4. Wait up to **3 seconds** for autocomplete suggestions to appear.
   - If suggestions appear → click the first one.
   - If no suggestions appear within 3 seconds → log a warning, skip row (no screenshot, no price), continue to next record.
5. After clicking, wait (bounded timeout) for the detail page to load — a URL change
   plus the price/instrument container being present. Timeout → treat as row failure
   (log warning, `Web_Price` empty, continue).
6. Extract the current price/rate from the detail page and **store it to the row's
   `Web_Price` immediately**.
   - If the price element is not found → log a warning, leave `Web_Price` empty.
7. Take a screenshot and save it to:
   ```
   <screenshots_dir>/<csv_stem>/<csv_stem>-<sanitized_instrument>-<row_index>.png
   ```
   Screenshot failure is logged independently and never discards an already-stored price.
8. Print result to stdout: `<instrument>: <price>`.

After all rows are processed, the CSV is written back **atomically** (see below).

---

## Screenshot Naming

- **Root folder:** `<screenshots_dir>/` (default: `screenshots/`)
- **Sub-folder:** `<csv_stem>/` — the CSV filename without extension (e.g. `positions` for `positions.csv`)
- **Filename:** `<csv_stem>-<sanitized_instrument>-<row_index>.png` (row index keeps
  duplicate instruments and sanitization collisions from overwriting each other)
- **Sanitization:** spaces → underscores, non-alphanumeric/underscore/hyphen chars stripped, lowercased

**Example:** CSV `positions.csv`, instrument `ASML Holding` at row 0 →  
`screenshots/positions/positions-asml_holding-0.png`

---

## CSV Write-Back

After processing all rows, the input CSV file is updated with all original columns
preserved plus one new appended column:

- **Column name:** `Web_Price`
- **Value:** the fetched price string for that instrument, or empty string if the
  instrument was blank, skipped, or the price could not be extracted.

**Atomic write:** results are written to a uniquely named temporary file in the same
directory, flushed and `fsync`'d, then `os.replace()`'d over the input only after
successful serialization. The temporary file is removed on failure. This prevents a
partial/empty CSV if the process crashes mid-write.

**CSV contract:**
- Opened with `newline=""`; read/written as UTF-8, tolerating a UTF-8 BOM on input
  (the `instrument` header is matched after BOM stripping).
- Uses `csv.DictReader`/`DictWriter`; the original column order is preserved.
- If a `Web_Price` column already exists in the input, its values are overwritten
  in place (not duplicated).

---

## Error Handling

| Situation | Behaviour |
|---|---|
| `instrument` column missing from CSV | Raise `ValueError` immediately, exit with code 1 |
| Empty CSV (no data rows) | Log info, exit cleanly |
| Blank/whitespace-only instrument value | Log warning, skip row, `Web_Price` left empty |
| No autocomplete suggestion within 3 seconds | Log warning, skip row, no screenshot, `Web_Price` left empty |
| Detail page fails to load after click | Log warning, `Web_Price` left empty, continue |
| Price element not found on page | Log warning, take screenshot anyway, `Web_Price` left empty, continue |
| Screenshot fails after price extracted | Log warning independently; keep the stored `Web_Price` |
| Any unhandled Playwright error per row | Log error, close page, continue to next row |

---

## Dependencies

New Python dependency:
- `playwright>=1.40` (Python bindings)

Chromium browser must be installed separately:
```bash
uv run playwright install chromium
```

This is documented in the README.

---

## Modules

### `instrument_search.py`

Key functions:

```python
async def search_instrument(page, instrument: str) -> bool:
    """Search MarketScreener, wait up to 3s for autocomplete, click first
    suggestion. Return True if a suggestion was selected, False if none appeared."""

async def extract_price(page) -> str | None:
    """Extract current price/rate from the instrument detail page."""

async def run_search(csv_path: Path, screenshots_dir: Path) -> int:
    """Main async loop. Reads CSV, initializes every row's Web_Price to "",
    launches Chromium once, processes each row by index on a fresh page (closed
    in finally), then atomically writes Web_Price back to the CSV.
    Returns 0 (success) or 1 (had errors)."""

def main(argv=None) -> int:
    """CLI entry point. Parses args, runs asyncio.run(run_search(...))."""
```

---

## Testing

- Unit tests for CSV reading (incl. BOM), atomic `Web_Price` write-back, row-index
  mapping with duplicate/failed rows, and filename sanitization (no browser needed).
- Async unit tests with a mocked/fake Playwright page covering: no-suggestion skip,
  detail-page load timeout, price-not-found, and screenshot-failure paths.
- Live integration test is out of scope (requires internet + Playwright install).
- Existing test suite remains unaffected.
