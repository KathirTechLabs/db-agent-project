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
    """Lowercase, spaces→underscores, strip chars except alphanum/underscore/hyphen."""
    name = name.lower().replace(" ", "_")
    name = re.sub(r"[^\w\-]", "", name)
    return name


def screenshot_path(
    screenshots_dir: Path, csv_stem: str, instrument: str, row_index: int
) -> Path:
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
# Playwright helpers
# ---------------------------------------------------------------------------


async def search_instrument(page, instrument: str) -> bool:
    """Fill the MarketScreener search, wait up to 3s for autocomplete, navigate to
    the first suggestion. Returns True if navigated, False if no suggestion appeared."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    # Fill via JS to bypass any overlay visibility issues
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
        logger.warning(
            "No autocomplete suggestion for %r within 3 seconds — skipping", instrument
        )
        return False

    href = await first_row.get_attribute("data-href")
    if not href:
        logger.warning(
            "First autocomplete row has no data-href for %r — skipping", instrument
        )
        return False

    await page.goto("https://nl.marketscreener.com" + href)
    await page.wait_for_load_state("domcontentloaded")
    return True


async def extract_price(page) -> str | None:
    """Extract the current price from the instrument detail page. Returns None if not found."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    try:
        price = page.locator(
            'td.is__realtime-last span[data-field="last"]'
        ).first
        text = await price.text_content(timeout=5000)
        return text.strip() if text else None
    except PlaywrightTimeout:
        return None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def run_search(csv_path: Path, screenshots_dir: Path) -> int:
    """Read CSV, search every instrument on MarketScreener, write Web_Price back.
    Launches Chromium once; opens a fresh page per row (closed in finally).
    Returns 0 on full success, 1 if any row had errors/skips."""
    from playwright.async_api import async_playwright
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    fieldnames, rows = read_csv_rows(csv_path)
    if not rows:
        logger.info("CSV %s has no data rows — nothing to do.", csv_path)
        return 0

    had_errors = False

    # Pre-initialize Web_Price for every row
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
                    had_errors = True
                    continue

                page = await browser.new_page()
                try:
                    # Navigate to homepage
                    await page.goto(
                        "https://nl.marketscreener.com/",
                        wait_until="domcontentloaded",
                    )

                    # Accept cookie consent if shown (non-blocking)
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
                        had_errors = True
                        continue

                    # Confirm we landed on a detail page (URL changed from /)
                    try:
                        await page.wait_for_function(
                            "() => window.location.pathname !== '/'",
                            timeout=5000,
                        )
                    except PlaywrightTimeout:
                        logger.warning(
                            "Row %d (%r): detail page did not load — skipping.",
                            idx,
                            instrument,
                        )
                        had_errors = True
                        continue

                    # Extract and store price immediately
                    price = await extract_price(page)
                    if price:
                        row["Web_Price"] = price
                        logger.info("Row %d (%r): price = %s", idx, instrument, price)
                    else:
                        logger.warning(
                            "Row %d (%r): price element not found on page.", idx, instrument
                        )
                        had_errors = True

                    print(f"{instrument}: {price or '(not found)'}")

                    # Screenshot — failure is independent; stored price is safe
                    shot = screenshot_path(screenshots_dir, csv_stem, instrument, idx)
                    shot.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        await page.screenshot(path=str(shot))
                        logger.info("Row %d: screenshot → %s", idx, shot)
                    except Exception as exc:
                        logger.warning("Row %d: screenshot failed: %s", idx, exc)
                        had_errors = True

                except PlaywrightTimeout as exc:
                    logger.error(
                        "Row %d (%r): Playwright timeout: %s", idx, instrument, exc
                    )
                    had_errors = True
                except Exception as exc:
                    logger.error(
                        "Row %d (%r): unexpected error: %s", idx, instrument, exc
                    )
                    had_errors = True
                finally:
                    await page.close()
        finally:
            await browser.close()

    write_csv_atomic(csv_path, fieldnames, rows)
    logger.info("Web_Price written back to %s", csv_path)
    return 1 if had_errors else 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="instrument-search",
        description="Search instrument prices on MarketScreener and write back to CSV.",
    )
    parser.add_argument("--csv", required=True, help="Path to the input CSV file.")
    parser.add_argument(
        "--screenshots-dir",
        default="screenshots",
        help="Root folder for screenshots (default: screenshots/).",
    )
    args = parser.parse_args(argv)
    return asyncio.run(run_search(Path(args.csv), Path(args.screenshots_dir)))
