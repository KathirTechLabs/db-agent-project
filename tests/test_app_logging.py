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
