#!/usr/bin/env python3
"""Start runner (breakout scanner) and Telegram bot together."""
from __future__ import annotations

import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("tvDatafeed").setLevel(logging.ERROR)


def _run_runner() -> None:
    from runner import main
    main()


if __name__ == "__main__":
    # runner runs in background thread (no asyncio signal requirements)
    t_runner = threading.Thread(target=_run_runner, name="runner", daemon=True)
    t_runner.start()

    logging.info("SEPA TradeBot started — runner + bot running")

    # bot must run in main thread (asyncio signal handler requirement)
    from bot import main as bot_main
    bot_main()
