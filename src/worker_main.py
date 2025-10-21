"""Entry point for ingestion worker."""
from __future__ import annotations

import asyncio

from .config import load_settings
from .ingestion.worker import worker_loop
from .logging import setup_logging


def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    asyncio.run(worker_loop(settings))


if __name__ == "__main__":
    main()
