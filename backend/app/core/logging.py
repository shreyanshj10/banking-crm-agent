"""Standard-library logging setup (no print statements anywhere).

Call `configure_logging()` once at process start (the scratch runner and the
FastAPI app both call it). Verbosity is driven by LOG_LEVEL (env / .env, default
INFO) so it can be turned up or down with no code change.

All app loggers live under the "banking_crm" namespace, e.g.
`logging.getLogger("banking_crm.agent")`.
"""

from __future__ import annotations

import logging

from app.config import settings

_CONFIGURED = False
ROOT_NAME = "banking_crm"


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger(ROOT_NAME)
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    _CONFIGURED = True
