import loggerhelper
import pytest

from radar.common import log as log_module


@pytest.fixture(autouse=True)
def restore_logger_config():
    # NOTE: log 是全域單例，測試後還原設定，避免影響其他測試
    original = loggerhelper.log.config
    yield
    loggerhelper.log.reconfigure(config=original)


def test_log_is_shared_loggerhelper_instance():
    assert log_module.log is loggerhelper.log


def test_setup_logging_sets_service_name():
    log_module.setup_logging("ingest")

    assert log_module.log.config.name == "ingest"


def test_setup_logging_returns_shared_logger():
    assert log_module.setup_logging("crawler") is loggerhelper.log


def test_setup_logging_only_changes_name():
    loggerhelper.log.reconfigure(level="WARNING")

    log_module.setup_logging("api")

    assert log_module.log.config.level == "WARNING"
