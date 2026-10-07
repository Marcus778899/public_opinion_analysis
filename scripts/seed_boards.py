"""建立初始看板（S1-08）。用法：make seed（API 需已啟動）"""

import os

from radar.api.seed import INITIAL_BOARDS, seed
from radar.common.log import log, setup_logging

DEFAULT_API_URL = "http://localhost:8000"


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("seed")
    api_url = os.environ.get("RADAR_API_URL", DEFAULT_API_URL)
    result = seed(api_url, INITIAL_BOARDS)
    log.info("boards created=%s skipped=%s", result.created, result.skipped)


if __name__ == "__main__":
    main()
