"""驗收 shadow-missing-model-exit（#215）：shadow 缺模型版本或資料夾時，log 說明並以非 0 結束。

在子行程跑 radar.ml.inference.main.main() 才看得到真正的結束碼；
模型載入、ClickHouse、Kafka 全換成會留下記號的 fake，不連任何服務。
compose 怎麼讓容器停住由 worker 決定，這裡不測 compose 寫法。
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

DRIVER = """
import types
import radar.ml.inference.main as m

def mark(name):
    print("CALLED:" + name, flush=True)

def fake_load_classifier(model_dir, **kwargs):
    mark("load_classifier")
    card = types.SimpleNamespace(model_version="v-test", label_version="l-test", max_chars=100)
    return object(), card

class FakeCH:
    def __init__(self, *a, **k):
        mark("ClickHouseClient")
    def close(self):
        pass

class FakeProducer:
    def __init__(self, *a, **k):
        mark("JsonProducer")
    def send(self, *a, **k):
        pass
    def flush(self, *a, **k):
        pass

class FakeConsumer:
    def __init__(self, *a, **k):
        mark("BatchConsumer")
    def run(self):
        mark("consumer_run")

class FakeRegistry:
    @staticmethod
    def new_client(conf):
        mark("SchemaRegistryClient")
        return object()

m.load_classifier = fake_load_classifier
m.ClickHouseClient = FakeCH
m.ClickHouseSettings = lambda: object()
m.SchemaRegistrySettings = lambda: types.SimpleNamespace(url='http://x')
m.load_cache = lambda *a, **k: 0
m.JsonProducer = FakeProducer
m.BatchConsumer = FakeConsumer
m.SchemaRegistryClient = FakeRegistry
m.make_avro_decoder = lambda *a, **k: None
m.DlqPublisher = lambda *a, **k: object()
m.get_kafka_settings = lambda: object()
m.main()
"""

HEAVY = ("load_classifier", "ClickHouseClient", "JsonProducer", "BatchConsumer", "consumer_run")


def run_main(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith("INFERENCE_")}
    base.update(env)
    return subprocess.run(
        [sys.executable, "-c", DRIVER],
        env=base,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=False,
    )


def output(proc: subprocess.CompletedProcess[str]) -> str:
    return proc.stdout + proc.stderr


def assert_nothing_started(proc: subprocess.CompletedProcess[str]) -> None:
    text = output(proc)
    for name in HEAVY:
        assert f"CALLED:{name}" not in text, f"{name} should not run"


def test_shadow_model_dir_not_exist_exits_nonzero_and_names_path(tmp_path: Path) -> None:
    missing = tmp_path / "models" / "no-such-version"
    proc = run_main({"INFERENCE_ROLE": "shadow", "INFERENCE_MODEL_DIR": str(missing)})
    assert proc.returncode != 0
    assert str(missing) in output(proc)
    assert "Traceback" not in output(proc)
    assert_nothing_started(proc)


def test_shadow_model_dir_not_exist_does_not_exit_zero_via_kafka(tmp_path: Path) -> None:
    proc = run_main({"INFERENCE_ROLE": "shadow", "INFERENCE_MODEL_DIR": str(tmp_path / "gone")})
    assert "CALLED:BatchConsumer" not in output(proc)
    assert proc.returncode != 0


def test_shadow_model_dir_unset_exits_nonzero_and_names_env_var() -> None:
    proc = run_main({"INFERENCE_ROLE": "shadow"})
    assert proc.returncode != 0
    assert "INFERENCE_SHADOW_MODEL_VERSION" in output(proc)
    assert "Traceback" not in output(proc)
    assert_nothing_started(proc)


def test_shadow_model_dir_empty_string_exits_nonzero_and_names_env_var() -> None:
    proc = run_main({"INFERENCE_ROLE": "shadow", "INFERENCE_MODEL_DIR": ""})
    assert proc.returncode != 0
    assert "INFERENCE_SHADOW_MODEL_VERSION" in output(proc)
    assert_nothing_started(proc)


def test_shadow_version_blank_in_compose_style_dir_exits_nonzero_and_names_env_var(
    tmp_path: Path,
) -> None:
    # compose 把空版本組成 "/app/models/"：父資料夾存在，但裡面沒有 model_card.json
    models_root = tmp_path / "models"
    models_root.mkdir()
    proc = run_main({"INFERENCE_ROLE": "shadow", "INFERENCE_MODEL_DIR": f"{models_root}/"})
    assert proc.returncode != 0
    assert "INFERENCE_SHADOW_MODEL_VERSION" in output(proc)
    assert "Traceback" not in output(proc)
    assert_nothing_started(proc)


def test_shadow_missing_model_logs_single_explanatory_line(tmp_path: Path) -> None:
    proc = run_main({"INFERENCE_ROLE": "shadow", "INFERENCE_MODEL_DIR": str(tmp_path / "nope")})
    lines = [ln for ln in output(proc).splitlines() if str(tmp_path / "nope") in ln]
    assert len(lines) >= 1


def test_shadow_with_model_dir_present_still_runs(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "v1"
    model_dir.mkdir(parents=True)
    (model_dir / "model_card.json").write_text("{}")
    proc = run_main({"INFERENCE_ROLE": "shadow", "INFERENCE_MODEL_DIR": str(model_dir)})
    assert proc.returncode == 0, output(proc)
    assert "CALLED:load_classifier" in output(proc)
    assert "CALLED:consumer_run" in output(proc)


def test_primary_does_not_precheck_model_dir_and_still_loads(tmp_path: Path) -> None:
    proc = run_main({"INFERENCE_ROLE": "primary", "INFERENCE_MODEL_DIR": str(tmp_path / "nope")})
    assert proc.returncode == 0, output(proc)
    assert "CALLED:load_classifier" in output(proc)
    assert "CALLED:consumer_run" in output(proc)


def test_primary_default_role_with_valid_dir_runs_normally(tmp_path: Path) -> None:
    proc = run_main({"INFERENCE_MODEL_DIR": str(tmp_path)})
    assert proc.returncode == 0, output(proc)
    assert "CALLED:consumer_run" in output(proc)
