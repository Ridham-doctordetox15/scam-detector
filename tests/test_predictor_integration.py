"""Integration test: ScamPredictor.load with a REAL onnxruntime session and a REAL ``tokenizers`` tokenizer.

The ONNX graph is a tiny hand-built one (no torch, no trained weights): logits = [-x, +x] with x = 0.05 * sum(token_id * mask), so a message
made of higher-id tokens gets a higher scam probability and padding cannot change the result. It checks file loading, input feeding,
padding, truncation and softmax, not model quality. Skipped when onnx / onnxruntime / tokenizers are not installed.
"""
import json

import numpy as np
import pytest

onnx = pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")
tokenizers = pytest.importorskip("tokenizers")

from onnx import TensorProto, helper  # noqa: E402

from src.inference.predictor import ScamPredictor  # noqa: E402

VOCAB = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3, "hello": 4, "friend": 5, "free": 40, "prize": 60, "<url>": 30}


def build_model(path, with_token_type_ids: bool = False) -> None:
    names = ["input_ids", "attention_mask"] + (["token_type_ids"] if with_token_type_ids else [])
    inputs = [helper.make_tensor_value_info(n, TensorProto.INT64, ["batch", "seq"]) for n in names]
    nodes = [
        helper.make_node("Cast", ["input_ids"], ["ids_f"], to=TensorProto.FLOAT),
        helper.make_node("Cast", ["attention_mask"], ["mask_f"], to=TensorProto.FLOAT),
        helper.make_node("Mul", ["ids_f", "mask_f"], ["masked"]),
        helper.make_node("ReduceSum", ["masked", "axes"], ["total"], keepdims=1),
        helper.make_node("Mul", ["total", "scale"], ["x"]),
        helper.make_node("Neg", ["x"], ["neg_x"]),
        helper.make_node("Concat", ["neg_x", "x"], ["logits"], axis=1),
    ]
    inits = [helper.make_tensor("axes", TensorProto.INT64, [1], [1]), helper.make_tensor("scale", TensorProto.FLOAT, [1], [0.05])]
    graph = helper.make_graph(nodes, "tiny", inputs, [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["batch", 2])], inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.save(model, str(path))


def build_tokenizer(path) -> None:
    from tokenizers import Tokenizer, models, pre_tokenizers, processors

    tok = Tokenizer(models.WordLevel(VOCAB, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    tok.post_processor = processors.TemplateProcessing(single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 2), ("[SEP]", 3)])
    tok.save(str(path))


@pytest.fixture()
def model_dir(tmp_path):
    build_model(tmp_path / "model_quantized.onnx")
    build_tokenizer(tmp_path / "tokenizer.json")
    (tmp_path / "inference_config.json").write_text(json.dumps(
        {"model_name": "tiny", "max_length": 16, "threshold": 0.5, "lowercase": True, "labels": ["safe", "scam"],
         "pad_token_id": 0, "pad_token": "[PAD]"}), encoding="utf-8")
    return tmp_path


def test_real_session_scores_and_thresholds(model_dir):
    pred = ScamPredictor.load(model_dir)
    calm = pred.predict("hello friend")
    spam = pred.predict("FREE PRIZE free prize")
    assert calm.scam_probability < spam.scam_probability
    x_calm, x_spam = 0.05 * (2 + 4 + 5 + 3), 0.05 * (2 + 40 + 60 + 40 + 60 + 3)
    assert calm.scam_probability == pytest.approx(1 / (1 + np.exp(-2 * x_calm)), rel=1e-5)
    assert spam.scam_probability == pytest.approx(1 / (1 + np.exp(-2 * x_spam)), rel=1e-5)
    assert spam.is_scam and calm.is_scam == (calm.scam_probability >= 0.5)


def test_padding_does_not_change_a_score(model_dir):
    pred = ScamPredictor.load(model_dir, batch_size=8)
    alone = pred.predict_proba(["hello friend"])[0]
    batched = pred.predict_proba(["hello friend", "free prize free prize free prize hello"])[0]
    assert alone == pytest.approx(batched, rel=1e-6)


def test_urls_are_masked_before_tokenizing(model_dir):
    pred = ScamPredictor.load(model_dir)
    a = pred.predict("hello http://evil.example/a")
    b = pred.predict("hello http://other.example/zzz?x=1")
    assert a.scam_probability == pytest.approx(b.scam_probability)         # both become the same <URL> token


def test_truncation_bounds_the_length(model_dir):
    pred = ScamPredictor.load(model_dir)
    long_text = " ".join(["prize"] * 500)
    p = pred.predict(long_text).scam_probability                          # max_length 16: cls + 14 tokens + sep
    x = 0.05 * (2 + 60 * 14 + 3)
    assert p == pytest.approx(1 / (1 + np.exp(-2 * x)), rel=1e-5)


def test_token_type_ids_are_fed_when_the_graph_wants_them(tmp_path):
    build_model(tmp_path / "model.onnx", with_token_type_ids=True)
    build_tokenizer(tmp_path / "tokenizer.json")
    (tmp_path / "inference_config.json").write_text(json.dumps({"model_name": "tiny", "max_length": 16, "threshold": 0.5}), encoding="utf-8")
    assert ScamPredictor.load(tmp_path).predict("hello").scam_probability > 0
