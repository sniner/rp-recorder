from __future__ import annotations

import argparse
import logging
import re
import sys

from datetime import datetime


def safe_int(text: str, default: int = 0) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


DATETIME_PATTERN = re.compile(
    r"\s*(\d{4})-(\d{2})-(\d{2})(\s+|[tT])((\d{1,2}):(\d{1,2})(:(\d{1,2}))?)?"
)
TIME_PATTERN = re.compile(r"\s*(\d{1,2}):(\d{1,2})(:(\d{1,2}))?")


def parse_datetime_arg(text: str) -> datetime:
    try:
        if m := DATETIME_PATTERN.match(text):
            g = m.groups()
            args = map(lambda v: safe_int(v), g[0:3] + g[5:7] + g[8:9])
            dt = datetime(*args)  # pyright: ignore[reportArgumentType]
        elif m := TIME_PATTERN.match(text):
            args = map(lambda v: safe_int(v), m.groups()[0:2] + m.groups()[3:4])
            now = datetime.now()
            dt = datetime(now.year, now.month, now.day, *args)  # pyright: ignore[reportArgumentType]
        else:
            raise ValueError
        return dt
    except ValueError:
        msg = f"Given date/time {text!r} is not valid. Expected format: [YYYY-MM-DD] HH:MM[:SS]"
        raise argparse.ArgumentTypeError(msg)


def setup_logger(loglevel: int = logging.INFO, logfile: str | None = None) -> None:
    logger_format = "%(asctime)s %(levelname)s -- %(message)s"
    if logfile:
        logging.basicConfig(filename=logfile, level=loglevel, format=logger_format)
    else:
        logging.basicConfig(stream=sys.stderr, level=loglevel, format=logger_format)


# vim: set et sw=4 ts=4:
