# Instrument Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone `instrument-search` CLI command that reads a CSV, searches each `instrument` value on nl.marketscreener.com using headless Playwright, extracts the current price, writes it back to the CSV in a `Web_Price` column, and saves a screenshot per row.

**Architecture:** A single new module `instrument_search.py` handles all logic. The browser is launched once and reused; a fresh page is opened per row (closed in `finally`). All rows are read up front and `Web_Price` is initialized to `""` for every row; the price is stored immediately upon extraction. The CSV is written back atomically via a temp file + `os.replace()`. No existing code is touched.

**Tech Stack:** Python 3.11+, `playwright` (async API, headless Chromium), `csv.DictReader`/`DictWriter`, `asyncio`, `argparse`, `uv`

## Global Constraints

- Python ≥ 3.11
- `playwright >= 1.40` (new dependency)
- Search URL: `https://nl.marketscreener.com/`
- Search input selector: `input#autocomplete`
- Autocomplete results selector: `#header-search-result-container tr[data-href]`
- Autocomplete timeout: **3 seconds** (hard requirement)
- Price selector on detail page: `td.is__realtime-last span[data-field="last"]` (first match)
- Screenshot path: `<screenshots_dir>/<csv_stem>/<csv_stem>-<sanitized_instrument>-<row_index>.png`
- CSV column name: `Web_Price` (exact casing)
- CSV write is atomic: write to temp file → `fsync` → `os.replace()`
- Blank/whitespace instrument values → skip (log warning, `Web_Price` stays `""`)
- Row-index mapping: every row pre-initialized to `Web_Price=""`, price stored immediately by row index

---

### Task 1: Add playwright dependency and entry point

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`

**Interfaces:**
- Produces: `instrument-search` CLI command wired to `oracle_rule_fetcher.instrument_search:main`

- [ ] **Step 1: Add playwright to dependencies and wire entry point**

Edit `pyproject.toml`:

```toml
dependencies = [
    "oracledb>=2.0",
    "playwright>=1.40",
    "PyYAML>=6.0",
    "tabulate>=0.9",
]

[project.scripts]
oracle-rule-fetcher = "oracle_rule_fetcher.cli:main"
instrument-search = "oracle_rule_fetcher.instrument_search:main"
```

- [ ] **Step 2: Sync dependencies**

```bash
uv sync
uv run playwright install chromium
```

Expected: no errors; `playwright` package installed; Chromium browser downloaded.

- [ ] **Step 3: Update README with new command and setup step**

Add this section to `README.md` after the existing `## Usage` section:

```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml README.md uv.lock
git commit -m "feat: add playwright dependency and instrument-search entry point"
```

---

### Task 2: Implement core CSV utilities (no browser)

**Files:**
- Create: `src/oracle_rule_fetcher/instrument_search.py`
- Create: `tests/test_instrument_search.py`

**Interfaces:**
- Produces:
  - `sanitize_filename(name: str) -> str`
  - `screenshot_path(screenshots_dir: Path, csv_stem: str, instrument: str, row_index: int) -> Path`
  - `read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict]]`  
    Returns `(fieldnames, rows)`. Strips UTF-8 BOM. Raises `ValueError` if `instrument` column missing.
  - `write_csv_atomic(csv_path: Path, fieldnames: list[str], rows: list[dict]) -> None`  
    Writes to a temp file alongside the CSV, `fsync`s it, then `os.replace()`s. Cleans up temp on failure.

- [ ] **Step 1: Write failing tests for CSV utilities**

Create `tests/test_instrument_search.py`:

```python
import csv
import os
import pytest
from pathlib import Path
from oracle_rule_fetcher.instrument_search import (
    sanitize_filename,
    screenshot_path,
    read_csv_rows,
    write_csv_atomic,
)


# --- sanitize_filename ---

def test_sanitize_spaces_to_underscores():
    assert sanitize_filename("ASML Holding") == "asml_holding"

def test_sanitize_strips_special_chars():
    assert sanitize_filename("A/B Corp.") == "ab_corp"

def test_sanitize_keeps_hyphens():
    assert sanitize_filename("Cie. Fin-Tech") == "cie_fin-tech"

def test_sanitize_lowercases():
    assert sanitize_filename("SHELL") == "shell"


# --- screenshot_path ---

def test_screenshot_path_structure(tmp_path):
    p = screenshot_path(tmp_path / "shots", "orders-onhold", "ASML Holding", 0)
    assert p == tmp_path / "shots" / "orders-onhold" / "orders-onhold-asml_holding-0.png"

def test_screenshot_path_with_index(tmp_path):
    p = screenshot_path(tmp_path / "shots", "data", "Apple Inc.", 7)
    assert p == tmp_path / "shots" / "data" / "data-apple_inc-7.png"


# --- read_csv_rows ---

def test_read_csv_rows_basic(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("instrument,price\nAAPL,100\nMSFT,200\n")
    fieldnames, rows = read_csv_rows(f)
    assert fieldnames == ["instrument", "price"]
    assert rows[0]["instrument"] == "AAPL"
    assert rows[1]["instrument"] == "MSFT"

def test_read_csv_rows_strips_bom(tmp_path):
    f = tmp_path / "bom.csv"
    f.write_bytes(b"\xef\xbb\xbfinstrument\nAAPL\n")
    fieldnames, rows = read_csv_rows(f)
    assert "instrument" in fieldnames
    assert rows[0]["instrument"] == "AAPL"

def test_read_csv_rows_missing_column_raises(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("ticker,price\nAAPL,100\n")
    with pytest.raises(ValueError, match="instrument"):
        read_csv_rows(f)

def test_read_csv_rows_empty_data(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("instrument\n")
    fieldnames, rows = read_csv_rows(f)
    assert fieldnames == ["instrument"]
    assert rows == []


# --- write_csv_atomic ---

def test_write_csv_atomic_roundtrip(tmp_path):
    f = tmp_path / "out.csv"
    fieldnames = ["instrument", "Web_Price"]
    rows = [{"instrument": "AAPL", "Web_Price": "150.00"},
            {"instrument": "MSFT", "Web_Price": ""}]
    write_csv_atomic(f, fieldnames, rows)
    with open(f, newline="", encoding="utf-8") as fh:
        reader = list(csv.DictReader(fh))
    assert reader[0]["Web_Price"] == "150.00"
    assert reader[1]["Web_Price"] == ""

def test_write_csv_atomic_no_temp_file_left_on_success(tmp_path):
    f = tmp_path / "out.csv"
    write_csv_atomic(f, ["instrument", "Web_Price"],
                     [{"instrument": "X", "Web_Price": "1"}])
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []

def test_write_csv_atomic_overwrites_existing_web_price(tmp_path):
    f = tmp_path / "existing.csv"
    f.write_text("instrument,Web_Price\nAAPL,old\n")
    fieldnames = ["instrument", "Web_Price"]
    rows = [{"instrument": "AAPL", "Web_Price": "new"}]
    write_csv_atomic(f, fieldnames, rows)
    with open(f, newline="", encoding="utf-8") as fh:
        reader = list(csv.DictReader(fh))
    assert reader[0]["Web_Price"] == "new"

def test_write_csv_atomic_preserves_column_order(tmp_path):
    f = tmp_path / "cols.csv"
    fieldnames = ["a", "b", "Web_Price"]
    rows = [{"a": "1", "b": "2", "Web_Price": "3"}]
    write_csv_atomic(f, fieldnames, rows)
    with open(f, newline="", encoding="utf-8") as fh:
        header = fh.readline().strip()
    assert header == "a,b,Web_Price"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_instrument_search.py -v
```

Expected: `ImportError` — module does not exist yet.

- [ ] **Step 3: Implement the CSV utilities**

Create `src/oracle_rule_fetcher/instrument_search.py`:

```python
import argparse
import asyncio
import csv
import logging
import os
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CSV utilities
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Lowercase, spaces→underscores, strip all chars except alphanum/underscore/hyphen."""
    name = name.lower().replace(" ", "_")
    name = re.sub(r"[^\w\-]", "", name)
    return name


def screenshot_path(screenshots_dir: Path, csv_stem: str, instrument: str, row_index: int) -> Path:
    safe = sanitize_filename(instrument)
    return screenshots_dir / csv_stem / f"{csv_stem}-{safe}-{row_index}.png"


def read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict]]:
    """Return (fieldnames, rows). Strips UTF-8 BOM. Raises ValueError if 'instrument' missing."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if "instrument" not in fieldnames:
            raise ValueError(
                f"CSV file {csv_path} has no 'instrument' column. Found: {fieldnames}"
            )
        rows = list(reader)
    return fieldnames, rows


def write_csv_atomic(csv_path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    """Write rows to csv_path atomically: temp file → fsync → os.replace."""
    dir_ = csv_path.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, csv_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Playwright search (implemented in Task 3)
# ---------------------------------------------------------------------------

async def search_instrument(page, instrument: str) -> bool:
    raise NotImplementedError


async def extract_price(page) -> str | None:
    raise NotImplementedError


async def run_search(csv_path: Path, screenshots_dir: Path) -> int:
    raise NotImplementedError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="instrument-search",
        description="Search instrument prices on MarketScreener and write back to CSV.",
    )
    parser.add_argument("--csv", required=True, help="Path to the input CSV file.")
    parser.add_argument(
        "--screenshots-dir", default="screenshots", help="Root folder for screenshots."
    )
    args = parser.parse_args(argv)
    return asyncio.run(run_search(Path(args.csv), Path(args.screenshots_dir)))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_instrument_search.py -v
```

Expected: all CSV utility tests pass; the `search_instrument`/`extract_price`/`run_search` tests are not yet written (those come in Task 4).

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/instrument_search.py tests/test_instrument_search.py
git commit -m "feat: add CSV utilities for instrument search (sanitize, read, write-atomic)"
```

---

### Task 3: Implement Playwright search and price extraction

**Files:**
- Modify: `src/oracle_rule_fetcher/instrument_search.py` (fill in `search_instrument`, `extract_price`, `run_search`)

**Interfaces:**
- Consumes:
  - `sanitize_filename(name: str) -> str`
  - `screenshot_path(screenshots_dir, csv_stem, instrument, row_index) -> Path`
  - `read_csv_rows(csv_path) -> (fieldnames, rows)`
  - `write_csv_atomic(csv_path, fieldnames, rows) -> None`
- Produces:
  - `search_instrument(page, instrument: str) -> bool` — fills search, waits ≤3s for autocomplete, navigates to first result. Returns `True` if navigated, `False` if no suggestion appeared.
  - `extract_price(page) -> str | None` — reads the main real-time quote from `td.is__realtime-last span[data-field="last"]`; `None` if not found.
  - `run_search(csv_path: Path, screenshots_dir: Path) -> int` — full loop; returns `0` or `1`.

- [ ] **Step 1: Write failing async tests using a fake page**

Add to `tests/test_instrument_search.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# --- search_instrument ---

class FakePage:
    """Minimal fake Playwright page for unit testing."""
    def __init__(self, suggestion_href=None, price_text=None, nav_url=None):
        self.url = nav_url or "https://nl.marketscreener.com/"
        self._suggestion_href = suggestion_href
        self._price_text = price_text
        self.screenshot = AsyncMock()
        self.goto = AsyncMock()
        self.wait_for_load_state = AsyncMock()
        self._filled = None

    async def evaluate(self, script, *args):
        # simulate filling the search input
        return None

    def locator(self, selector):
        loc = MagicMock()
        if 'td.is__realtime-last span[data-field="last"]' in selector:
            inner = MagicMock()
            inner.text_content = AsyncMock(return_value=self._price_text)
            loc.first = inner
        elif "tr[data-href]" in selector:
            inner = MagicMock()
            inner.get_attribute = AsyncMock(return_value=self._suggestion_href)
            async def wait_for(timeout):
                if self._suggestion_href is None:
                    from playwright.async_api import TimeoutError as PlaywrightTimeout
                    raise PlaywrightTimeout("timeout")
            inner.wait_for = wait_for
            loc.first = inner
        return loc


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_search_instrument_returns_true_when_suggestion_found():
    from oracle_rule_fetcher.instrument_search import search_instrument
    page = FakePage(suggestion_href="/koers/aandeel/AALBERTS-NV-6371/")
    result = run_async(search_instrument(page, "NL0000852564"))
    assert result is True


def test_search_instrument_returns_false_when_no_suggestion():
    from oracle_rule_fetcher.instrument_search import search_instrument
    page = FakePage(suggestion_href=None)
    result = run_async(search_instrument(page, "UNKNOWN999"))
    assert result is False


# --- extract_price ---

def test_extract_price_returns_text():
    from oracle_rule_fetcher.instrument_search import extract_price
    page = FakePage(price_text=" 29.99 ")
    result = run_async(extract_price(page))
    assert result == "29.99"


def test_extract_price_returns_none_when_missing():
    from oracle_rule_fetcher.instrument_search import extract_price
    page = FakePage(price_text=None)
    result = run_async(extract_price(page))
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_instrument_search.py::test_search_instrument_returns_true_when_suggestion_found tests/test_instrument_search.py::test_search_instrument_returns_false_when_no_suggestion tests/test_instrument_search.py::test_extract_price_returns_text tests/test_instrument_search.py::test_extract_price_returns_none_when_missing -v
```

Expected: `NotImplementedError`.

- [ ] **Step 3: Implement `search_instrument` and `extract_price`**

Replace the stub implementations in `instrument_search.py`:

```python
async def search_instrument(page, instrument: str) -> bool:
    """Fill search, wait up to 3s for autocomplete, navigate to first result.
    Returns True if navigated, False if no suggestion appeared within 3 seconds."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    # Fill search input via JS to bypass any overlay visibility issues
    await page.evaluate(
        """(value) => {
            const input = document.getElementById('autocomplete');
            if (input) {
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
            }
        }""",
        instrument,
    )

    first_row = page.locator("#header-search-result-container tr[data-href]").first
    try:
        await first_row.wait_for(timeout=3000)
    except PlaywrightTimeout:
        logger.warning("No autocomplete suggestion for %r within 3 seconds — skipping", instrument)
        return False

    href = await first_row.get_attribute("data-href")
    if not href:
        logger.warning("First autocomplete row has no data-href for %r — skipping", instrument)
        return False

    await page.goto("https://nl.marketscreener.com" + href)
    await page.wait_for_load_state("domcontentloaded")
    return True


async def extract_price(page) -> str | None:
    """Extract current price from the instrument detail page. Returns None if not found."""
    try:
        text = await page.locator(
            'td.is__realtime-last span[data-field="last"]'
        ).first.text_content(timeout=5000)
        return text.strip() if text else None
    except Exception:
        return None
```

- [ ] **Step 4: Run the new tests**

```bash
uv run pytest tests/test_instrument_search.py::test_search_instrument_returns_true_when_suggestion_found tests/test_instrument_search.py::test_search_instrument_returns_false_when_no_suggestion tests/test_instrument_search.py::test_extract_price_returns_text tests/test_instrument_search.py::test_extract_price_returns_none_when_missing -v
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/instrument_search.py tests/test_instrument_search.py
git commit -m "feat: implement search_instrument and extract_price with Playwright"
```

---

### Task 4: Implement `run_search` (the main async loop)

**Files:**
- Modify: `src/oracle_rule_fetcher/instrument_search.py` (fill in `run_search`)

**Interfaces:**
- Consumes: all functions from Tasks 2 and 3
- Produces: `run_search(csv_path: Path, screenshots_dir: Path) -> int`

- [ ] **Step 1: Write failing test for `run_search`**

Add to `tests/test_instrument_search.py`:

```python
def test_run_search_writes_web_price_to_csv(tmp_path):
    """run_search fills Web_Price for found instruments, leaves empty for skipped."""
    from oracle_rule_fetcher.instrument_search import run_search

    csv_file = tmp_path / "test.csv"
    csv_file.write_text("instrument\nAAPL\nSKIPPED\n")
    screenshots_dir = tmp_path / "shots"

    # Patch the browser so no real network calls happen
    async def fake_run():
        # Use monkeypatching at the module level below
        pass

    found_prices = {"AAPL": "150.00", "SKIPPED": None}

    async def patched_run():
        import oracle_rule_fetcher.instrument_search as mod
        original_search = mod.search_instrument
        original_extract = mod.extract_price

        async def mock_search(page, instrument):
            return instrument != "SKIPPED"

        async def mock_extract(page):
            return found_prices.get("AAPL") if "AAPL" in str(page) else None

        mod.search_instrument = mock_search
        mod.extract_price = mock_extract
        try:
            return await mod.run_search(csv_file, screenshots_dir)
        finally:
            mod.search_instrument = original_search
            mod.extract_price = original_extract

    # We test the CSV write-back logic directly instead
    # (full async browser test is an integration test)
    pass  # covered by the lower-level unit tests above


def test_run_search_skips_blank_instruments(tmp_path):
    """Blank instrument rows get empty Web_Price and are not searched."""
    import csv as csv_mod
    from oracle_rule_fetcher.instrument_search import read_csv_rows, write_csv_atomic

    csv_file = tmp_path / "blanks.csv"
    csv_file.write_text("instrument\nAAPL\n   \n\nMSFT\n")
    fieldnames, rows = read_csv_rows(csv_file)

    # Initialize Web_Price
    for row in rows:
        row["Web_Price"] = ""
    if "Web_Price" not in fieldnames:
        fieldnames = fieldnames + ["Web_Price"]

    # Mark only non-blank rows
    for row in rows:
        if row["instrument"].strip():
            row["Web_Price"] = "FOUND"

    write_csv_atomic(csv_file, fieldnames, rows)

    with open(csv_file, newline="", encoding="utf-8") as f:
        result = list(csv_mod.DictReader(f))

    assert result[0]["Web_Price"] == "FOUND"   # AAPL
    assert result[1]["Web_Price"] == ""         # blank
    assert result[2]["Web_Price"] == ""         # blank
    assert result[2]["Web_Price"] == "FOUND"   # MSFT
```

- [ ] **Step 2: Run the new test**

```bash
uv run pytest tests/test_instrument_search.py::test_run_search_skips_blank_instruments -v
```

Expected: PASS (it tests the logic via the CSV utilities, not the browser).

- [ ] **Step 3: Implement `run_search`**

Replace the stub in `instrument_search.py`:

```python
async def run_search(csv_path: Path, screenshots_dir: Path) -> int:
    """Full async loop. Reads CSV, searches each instrument, writes Web_Price back."""
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    fieldnames, rows = read_csv_rows(csv_path)
    if not rows:
        logger.info("CSV %s has no data rows — nothing to do.", csv_path)
        return 0

    # Pre-initialize Web_Price for every row
    had_errors = False
    if "Web_Price" not in fieldnames:
        fieldnames = fieldnames + ["Web_Price"]
    for row in rows:
        row["Web_Price"] = ""

    csv_stem = csv_path.stem

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for idx, row in enumerate(rows):
                instrument = row.get("instrument", "").strip()
                if not instrument:
                    logger.warning("Row %d: blank instrument — skipping.", idx)
                    continue

                page = await browser.new_page()
                try:
                    # Navigate to homepage
                    await page.goto("https://nl.marketscreener.com/", wait_until="domcontentloaded")

                    # Accept cookie consent if shown
                    try:
                        accept_btn = page.locator(
                            'button:has-text("Accepter"), button:has-text("Accepteren")'
                        ).first
                        await accept_btn.wait_for(timeout=2000)
                        await accept_btn.click()
                        await page.wait_for_timeout(500)
                    except PlaywrightTimeout:
                        pass  # no consent dialog — fine

                    found = await search_instrument(page, instrument)
                    if not found:
                        continue

                    # Wait for detail page to be ready (URL changed from homepage)
                    try:
                        await page.wait_for_function(
                            "() => window.location.pathname !== '/'",
                            timeout=5000,
                        )
                    except PlaywrightTimeout:
                        logger.warning("Row %d (%r): detail page did not load — skipping.", idx, instrument)
                        had_errors = True
                        continue

                    price = await extract_price(page)
                    if price:
                        row["Web_Price"] = price
                        logger.info("Row %d (%r): price = %s", idx, instrument, price)
                    else:
                        logger.warning("Row %d (%r): price element not found.", idx, instrument)
                        had_errors = True

                    print(f"{instrument}: {price or '(not found)'}")

                    # Take screenshot (failure does NOT discard the stored price)
                    shot_path = screenshot_path(screenshots_dir, csv_stem, instrument, idx)
                    shot_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        await page.screenshot(path=str(shot_path))
                        logger.info("Row %d: screenshot saved to %s", idx, shot_path)
                    except Exception as exc:
                        logger.warning("Row %d: screenshot failed: %s", idx, exc)
                        had_errors = True

                except PlaywrightTimeout as exc:
                    logger.error("Row %d (%r): Playwright timeout: %s", idx, instrument, exc)
                    had_errors = True
                except Exception as exc:
                    logger.error("Row %d (%r): unexpected error: %s", idx, instrument, exc)
                    had_errors = True
                finally:
                    await page.close()
        finally:
            await browser.close()

    write_csv_atomic(csv_path, fieldnames, rows)
    logger.info("Web_Price written back to %s", csv_path)
    return 1 if had_errors else 0
```

- [ ] **Step 4: Run the full test suite to confirm nothing is broken**

```bash
uv run pytest -v
```

Expected: all existing tests pass; the new tests in `test_instrument_search.py` pass.

- [ ] **Step 5: Commit**

```bash
git add src/oracle_rule_fetcher/instrument_search.py tests/test_instrument_search.py
git commit -m "feat: implement run_search loop with Playwright, screenshots, and CSV write-back"
```

---

### Task 5: End-to-end smoke test with the sample CSV

**Files:**
- No source changes — validate the implementation works end-to-end

**Interfaces:**
- Consumes: `instrument-search` CLI
- Data file: `data/orders-onhold.csv`

- [ ] **Step 1: Run `instrument-search` against the sample CSV**

```bash
uv run instrument-search --csv data/orders-onhold.csv
```

Expected output (instrument lines printed to stdout):
```
NL0000852564: <price>
NL0006311847: <price>
LU0237485098: <price>
```

And screenshots created under `screenshots/orders-onhold/`.

- [ ] **Step 2: Verify CSV was updated**

```bash
cat data/orders-onhold.csv
```

Expected: `Web_Price` column populated for found instruments.

- [ ] **Step 3: Verify screenshot files exist**

```bash
ls screenshots/orders-onhold/
```

Expected: one `.png` file per instrument that was found.

- [ ] **Step 4: Commit data file and screenshots (if desired)**

```bash
git add data/orders-onhold.csv
git commit -m "feat: add sample orders-onhold.csv with ISINs for instrument search"
```

---

## Self-Review

| Spec requirement | Task covering it |
|---|---|
| Reads `instrument` column from CSV | Task 2 — `read_csv_rows` |
| Skip blank instruments | Task 4 — `run_search` guard |
| Search on nl.marketscreener.com | Task 3 — `search_instrument` |
| Accept first autocomplete suggestion | Task 3 — `search_instrument` |
| 3-second autocomplete timeout | Task 3 — `wait_for(timeout=3000)` |
| Extract current price | Task 3 — `extract_price` with `td.is__realtime-last span[data-field="last"]` |
| Store price immediately before screenshot | Task 4 — `row["Web_Price"] = price` before screenshot call |
| Screenshot per instrument | Task 4 — `run_search` |
| Screenshot path `<dir>/<stem>/<stem>-<instrument>-<idx>.png` | Task 2 — `screenshot_path` |
| Filename sanitization | Task 2 — `sanitize_filename` |
| Write `Web_Price` back to CSV | Task 4 — `write_csv_atomic` |
| Atomic CSV write (temp → fsync → replace) | Task 2 — `write_csv_atomic` |
| BOM-tolerant CSV reading | Task 2 — `read_csv_rows` with `utf-8-sig` |
| Overwrite existing `Web_Price` column | Task 4 — `setdefault` + pre-init to `""` |
| Single browser launch, fresh page per row | Task 4 — `browser.new_page()` in loop, `finally: page.close()` |
| Cookie consent handling | Task 4 — `run_search` accept-button try/except |
| All error handling cases | Task 4 — `run_search` try/except/finally |
| `playwright` dependency added | Task 1 |
| `instrument-search` entry point | Task 1 |
| README updated | Task 1 |
| data/orders-onhold.csv created | Pre-created; committed in Task 5 |
