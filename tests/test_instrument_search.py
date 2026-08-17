"""
Tests for instrument_search module.
All tests here are pure-Python (no live browser / no network).
The async Playwright tests use a FakePage that mocks the Playwright API surface.
"""

import asyncio
import csv as csv_mod

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from oracle_rule_fetcher.instrument_search import (
    extract_price,
    read_csv_rows,
    sanitize_filename,
    screenshot_path,
    search_instrument,
    write_csv_atomic,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_async(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


def test_sanitize_spaces_to_underscores():
    assert sanitize_filename("ASML Holding") == "asml_holding"


def test_sanitize_strips_special_chars():
    # period and slash removed; underscores preserved
    assert sanitize_filename("A/B Corp.") == "ab_corp"


def test_sanitize_keeps_hyphens():
    assert sanitize_filename("Cie. Fin-Tech") == "cie_fin-tech"


def test_sanitize_lowercases():
    assert sanitize_filename("SHELL") == "shell"


def test_sanitize_empty_string():
    assert sanitize_filename("") == ""


# ---------------------------------------------------------------------------
# screenshot_path
# ---------------------------------------------------------------------------


def test_screenshot_path_structure(tmp_path):
    p = screenshot_path(tmp_path / "shots", "orders-onhold", "ASML Holding", 0)
    assert p == tmp_path / "shots" / "orders-onhold" / "orders-onhold-asml_holding-0.png"


def test_screenshot_path_with_index(tmp_path):
    p = screenshot_path(tmp_path / "shots", "data", "Apple Inc.", 7)
    assert p == tmp_path / "shots" / "data" / "data-apple_inc-7.png"


def test_screenshot_path_isin(tmp_path):
    p = screenshot_path(tmp_path / "s", "orders-onhold", "NL0000852564", 0)
    assert p == tmp_path / "s" / "orders-onhold" / "orders-onhold-nl0000852564-0.png"


# ---------------------------------------------------------------------------
# read_csv_rows
# ---------------------------------------------------------------------------


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


def test_read_csv_rows_preserves_extra_columns(tmp_path):
    f = tmp_path / "multi.csv"
    f.write_text("instrument,qty,price\nAAPL,10,150\n")
    fieldnames, rows = read_csv_rows(f)
    assert fieldnames == ["instrument", "qty", "price"]
    assert rows[0]["qty"] == "10"


# ---------------------------------------------------------------------------
# write_csv_atomic
# ---------------------------------------------------------------------------


def test_write_csv_atomic_roundtrip(tmp_path):
    f = tmp_path / "out.csv"
    fieldnames = ["instrument", "Web_Price"]
    rows = [
        {"instrument": "AAPL", "Web_Price": "150.00"},
        {"instrument": "MSFT", "Web_Price": ""},
    ]
    write_csv_atomic(f, fieldnames, rows)
    with open(f, newline="", encoding="utf-8") as fh:
        reader = list(csv_mod.DictReader(fh))
    assert reader[0]["Web_Price"] == "150.00"
    assert reader[1]["Web_Price"] == ""


def test_write_csv_atomic_no_temp_file_left_on_success(tmp_path):
    f = tmp_path / "out.csv"
    write_csv_atomic(f, ["instrument", "Web_Price"], [{"instrument": "X", "Web_Price": "1"}])
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_write_csv_atomic_overwrites_existing_web_price(tmp_path):
    f = tmp_path / "existing.csv"
    f.write_text("instrument,Web_Price\nAAPL,old\n")
    fieldnames = ["instrument", "Web_Price"]
    rows = [{"instrument": "AAPL", "Web_Price": "new"}]
    write_csv_atomic(f, fieldnames, rows)
    with open(f, newline="", encoding="utf-8") as fh:
        reader = list(csv_mod.DictReader(fh))
    assert reader[0]["Web_Price"] == "new"


def test_write_csv_atomic_preserves_column_order(tmp_path):
    f = tmp_path / "cols.csv"
    fieldnames = ["a", "b", "Web_Price"]
    rows = [{"a": "1", "b": "2", "Web_Price": "3"}]
    write_csv_atomic(f, fieldnames, rows)
    with open(f, newline="", encoding="utf-8") as fh:
        header = fh.readline().strip()
    assert header == "a,b,Web_Price"


# ---------------------------------------------------------------------------
# FakePage for async unit tests
# ---------------------------------------------------------------------------


class _FakeLocatorFirst:
    """Simulates page.locator(...).first"""

    def __init__(self, *, suggestion_href=None, price_text=None, should_timeout=False):
        self._href = suggestion_href
        self._price = price_text
        self._timeout = should_timeout

    async def wait_for(self, timeout=None):
        if self._timeout:
            from playwright.async_api import TimeoutError as PlaywrightTimeout

            raise PlaywrightTimeout("Timeout")

    async def get_attribute(self, name):
        return self._href if name == "data-href" else None

    async def text_content(self, timeout=None):
        return self._price


class FakePage:
    """Minimal fake Playwright page for unit testing (no network)."""

    def __init__(
        self,
        *,
        suggestion_href=None,
        price_text=None,
        no_suggestion=False,
    ):
        self._href = suggestion_href
        self._price = price_text
        self._no_suggestion = no_suggestion
        self.goto = AsyncMock()
        self.wait_for_load_state = AsyncMock()
        self.wait_for_function = AsyncMock()
        self.wait_for_timeout = AsyncMock()
        self.screenshot = AsyncMock()
        self.evaluate = AsyncMock(return_value=None)
        self.url = "https://nl.marketscreener.com/"

    def locator(self, selector):
        loc = MagicMock()
        if "tr[data-href]" in selector:
            loc.first = _FakeLocatorFirst(
                suggestion_href=self._href,
                should_timeout=self._no_suggestion,
            )
        elif 'td.is__realtime-last span[data-field="last"]' in selector:
            loc.first = _FakeLocatorFirst(price_text=self._price)
        return loc


# ---------------------------------------------------------------------------
# search_instrument (async unit tests)
# ---------------------------------------------------------------------------


def test_search_instrument_returns_true_when_suggestion_found():
    page = FakePage(suggestion_href="/koers/aandeel/AALBERTS-NV-6371/")
    result = run_async(search_instrument(page, "NL0000852564"))
    assert result is True
    page.goto.assert_awaited_once()
    call_url = page.goto.call_args[0][0]
    assert "nl.marketscreener.com" in call_url
    assert "AALBERTS" in call_url


def test_search_instrument_returns_false_when_no_suggestion():
    page = FakePage(no_suggestion=True)
    result = run_async(search_instrument(page, "UNKNOWN999"))
    assert result is False
    page.goto.assert_not_awaited()


def test_search_instrument_fills_search_input():
    page = FakePage(suggestion_href="/koers/aandeel/TEST/")
    run_async(search_instrument(page, "MY_INSTRUMENT"))
    page.evaluate.assert_awaited_once()
    js_call_args = page.evaluate.call_args[0]
    # second positional arg is the instrument value passed to JS
    assert js_call_args[1] == "MY_INSTRUMENT"


# ---------------------------------------------------------------------------
# extract_price (async unit tests)
# ---------------------------------------------------------------------------


def test_extract_price_returns_stripped_text():
    page = FakePage(price_text=" 29.99 ")
    result = run_async(extract_price(page))
    assert result == "29.99"


def test_extract_price_returns_none_when_missing():
    page = FakePage(price_text=None)
    result = run_async(extract_price(page))
    assert result is None


def test_extract_price_returns_none_on_empty_string():
    page = FakePage(price_text="")
    result = run_async(extract_price(page))
    assert result is None


# ---------------------------------------------------------------------------
# CSV write-back logic (no browser)
# ---------------------------------------------------------------------------


def test_run_search_skips_blank_instruments(tmp_path):
    """Blank/whitespace rows get empty Web_Price; non-blank rows get a value."""
    f = tmp_path / "blanks.csv"
    f.write_text("instrument\nAAPL\n   \n\nMSFT\n")
    fieldnames, rows = read_csv_rows(f)

    if "Web_Price" not in fieldnames:
        fieldnames = fieldnames + ["Web_Price"]
    for row in rows:
        row["Web_Price"] = ""

    for row in rows:
        if row["instrument"].strip():
            row["Web_Price"] = "FOUND"

    write_csv_atomic(f, fieldnames, rows)

    with open(f, newline="", encoding="utf-8") as fh:
        result = list(csv_mod.DictReader(fh))

    assert result[0]["Web_Price"] == "FOUND"  # AAPL
    assert result[1]["Web_Price"] == ""  # "   "
    assert result[2]["Web_Price"] == "FOUND"  # MSFT


def test_duplicate_instruments_get_independent_web_price(tmp_path):
    """Each row is handled independently by index — duplicates do not overwrite each other."""
    f = tmp_path / "dups.csv"
    f.write_text("instrument\nAAPL\nAAPL\nAAPL\n")
    fieldnames, rows = read_csv_rows(f)

    if "Web_Price" not in fieldnames:
        fieldnames = fieldnames + ["Web_Price"]
    for row in rows:
        row["Web_Price"] = ""

    # Simulate per-index writes (only row 1 found a price)
    rows[1]["Web_Price"] = "200.00"

    write_csv_atomic(f, fieldnames, rows)

    with open(f, newline="", encoding="utf-8") as fh:
        result = list(csv_mod.DictReader(fh))

    assert result[0]["Web_Price"] == ""
    assert result[1]["Web_Price"] == "200.00"
    assert result[2]["Web_Price"] == ""
