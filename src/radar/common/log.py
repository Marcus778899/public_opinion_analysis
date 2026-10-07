"""專案唯一的 log 入口，包裝 loggerhelper；各模組一律 `from radar.common.log import log`。"""

from loggerhelper import Logger, configure, log

__all__ = ["log", "setup_logging"]


def setup_logging(service: str) -> Logger:
    """服務入口在第一行 log 前呼叫一次，讓每行 log 帶上服務名稱；其餘設定沿用 LOG_* 環境變數。"""
    return configure(name=service)
