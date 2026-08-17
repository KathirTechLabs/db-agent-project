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
