"""Shared logger used by every module."""

import logging
import sys
from pathlib import Path
from config import LOG_DIR


def get_logger(name: str = "cv_scraper") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger   # already configured

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File — DEBUG and above (full trace)
    fh = logging.FileHandler(LOG_DIR / "scraper.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
