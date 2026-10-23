from types import SimpleNamespace

import pytest

from videoflow.hw import ai
from videoflow.hw.ai import Device, NoProviderError, build_chain, make_session

ALL = [
    "VitisAIExecutionProvider", "QNNExecutionProvider", "CUDAExecutionProvider",
    "DmlExecutionProvider", "OpenVINOExecutionProvider", "ROCMExecutionProvider",
    "MIGraphXExecutionProvider", "CPUExecutionProvider",
]  # fmt: skip


def labels(chain):
    return [c.label for c in chain]


def test_full_order_auto():
    chain = build_chain(ALL, ["CPU", "GPU", "NPU"])
    assert labels(chain) == [
        "OpenVINOExecutionProvider:NPU",
        "VitisAIExecutionProvider",
        "QNNExecutionProvider",
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "OpenVINOExecutionProvider:GPU",
        "ROCMExecutionProvider",
        "MIGraphXExecutionProvider",
        "CPUExecutionProvider",
    ]
    assert [c.device for c in chain[:3]] == [Device.NPU] * 3
    assert chain[-1].device is Device.CPU


def test_openvino_needs_device_listing():
    chain = build_chain(["OpenVINOExecutionProvider", "CPUExecutionProvider"], None)
    assert labels(chain) == ["CPUExecutionProvider"]
    chain = build_chain(["OpenVINOExecutionProvider", "CPUExecutionProvider"], ["CPU", "GPU"])
    assert labels(chain) == ["OpenVINOExecutionProvider:GPU", "CPUExecutionProvider"]


def test_prefer_tiers():
    ov = ["NPU", "GPU"]
    prov = ["OpenVINOExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
    assert labels(build_chain(prov, ov, "gpu")) == [
        "CUDAExecutionProvider",
        "OpenVINOExecutionProvider:GPU",
        "CPUExecutionProvider",
    ]
    assert labels(build_chain(prov, ov, "cpu")) == ["CPUExecutionProvider"]
    assert build_chain(prov, ov, "npu")[0].device is Device.NPU


class FakeInput:
    def __init__(self, name="x", shape=(None, 3), type_="tensor(float)"):
        self.name, self.shape, self.type = name, list(shape), type_


def fake_ort(failing: dict[str, str], silent_fallback: set[str] = frozenset()):
    """Sessions fail at creation or at run according to `failing` (provider -> 'create'|'run')."""
    created: list[str] = []

    class Session:
        def __init__(self, path, sess_options=None, providers=None):
            self.name = providers[0][0] if isinstance(providers[0], tuple) else providers[0]
            created.append(self.name)
            if failing.get(self.name) == "create":
                raise RuntimeError("cannot init")
            self.ran = None

        def get_providers(self):
            if self.name in silent_fallback:
                return ["CPUExecutionProvider"]
            return [self.name]

        def get_inputs(self):
            return [FakeInput()]

        def run(self, _out, feeds):
            if failing.get(self.name) == "run":
                raise RuntimeError("unsupported operator")
            self.ran = feeds
            return []

    mod = SimpleNamespace(
        InferenceSession=Session, SessionOptions=lambda: object(), __version__="fake"
    )
    mod.created = created  # type: ignore[attr-defined]
    return mod


def test_fallback_on_create_and_warmup_failure(monkeypatch):
    mod = fake_ort({"CUDAExecutionProvider": "create", "VitisAIExecutionProvider": "run"})
    monkeypatch.setattr(ai, "_import_ort", lambda: mod)
    chain = build_chain(
        ["VitisAIExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"], None
    )
    ms = make_session("m.onnx", chain=chain)
    assert ms.device is Device.CPU
    assert [a.error is None for a in ms.attempts] == [False, False, True]
    assert "unsupported operator" in (ms.attempts[0].error or "")
    assert ms.session.ran["x"].shape == (1, 3)  # dynamic dim replaced


def test_silent_cpu_fallback_is_detected(monkeypatch):
    mod = fake_ort({}, silent_fallback={"CUDAExecutionProvider"})
    monkeypatch.setattr(ai, "_import_ort", lambda: mod)
    chain = build_chain(["CUDAExecutionProvider", "CPUExecutionProvider"], None)
    ms = make_session("m.onnx", chain=chain)
    assert ms.device is Device.CPU and ms.attempts[0].error


def test_per_model_independence(monkeypatch):
    bad = {"CUDAExecutionProvider": "run"}
    chain = build_chain(["CUDAExecutionProvider", "CPUExecutionProvider"], None)
    monkeypatch.setattr(ai, "_import_ort", lambda: fake_ort(bad))
    assert make_session("a.onnx", chain=chain).device is Device.CPU
    monkeypatch.setattr(ai, "_import_ort", lambda: fake_ort({}))
    assert make_session("b.onnx", chain=chain).device is Device.GPU


def test_all_fail_raises(monkeypatch):
    monkeypatch.setattr(ai, "_import_ort", lambda: fake_ort({"CPUExecutionProvider": "run"}))
    with pytest.raises(NoProviderError, match="CPUExecutionProvider"):
        make_session("m.onnx", chain=build_chain(["CPUExecutionProvider"], None))


def test_missing_onnxruntime(monkeypatch):
    monkeypatch.setattr(ai, "_import_ort", lambda: None)
    assert ai.available_providers() == []
    with pytest.raises(NoProviderError, match="not installed"):
        make_session("m.onnx")
    assert ai.describe_ai()["onnxruntime"] is None


def test_probe_uses_ort_listing(monkeypatch):
    mod = SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"])
    monkeypatch.setattr(ai, "_import_ort", lambda: mod)
    monkeypatch.setattr(ai, "_import_openvino", lambda: None)
    assert labels(ai.probe_chain()) == ["CPUExecutionProvider"]
    assert ai.openvino_devices() is None


def test_real_cpu_session(tmp_path):
    onnx = pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from onnx import TensorProto, helper

    x = helper.make_tensor_value_info("x", TensorProto.FLOAT, ["batch", 4])
    y = helper.make_tensor_value_info("y", TensorProto.FLOAT, ["batch", 4])
    model = helper.make_model(
        helper.make_graph([helper.make_node("Relu", ["x"], ["y"])], "g", [x], [y]),
        opset_imports=[helper.make_opsetid("", 13)],
    )
    model.ir_version = 9
    path = tmp_path / "relu.onnx"
    onnx.save(model, str(path))
    ms = make_session(path, prefer="cpu")
    assert ms.device is Device.CPU
    import numpy as np

    out = ms.session.run(None, {"x": np.array([[-1, 2, -3, 4]], dtype=np.float32)})[0]
    assert out.tolist() == [[0, 2, 0, 4]]
    assert make_session(path, prefer="auto").device in Device
