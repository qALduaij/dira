"""Bound long-running native service logs without buffering their output in RAM."""

import logging
from logging.handlers import RotatingFileHandler
import sys


def main():
    handler = RotatingFileHandler(sys.argv[1], maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("service-output")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        for line in sys.stdin:
            logger.info("%s", line.rstrip())
    finally:
        handler.close()


if __name__ == "__main__":
    main()
