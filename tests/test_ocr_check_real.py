"""Tests for src.ocr.check_real_screenshots with a fake analyze function (no OCR, no models)."""
from __future__ import annotations

from types import SimpleNamespace

from src.ocr import check_real_screenshots as C
from src.ocr.ocr import NoTextFoundError, OCRResult
from src.ocr.validate import InvalidImageError


def _fake_result(text: str, verdict: str = "scam"):
    return SimpleNamespace(
        ocr=OCRResult(text=text, raw_text=text, mean_confidence=0.8, num_boxes=4, languages=("en", "hi")),
        explain_result=SimpleNamespace(output=SimpleNamespace(verdict=verdict, risk_level="high"), path="template"),
        prediction=SimpleNamespace(scam_probability=0.91),
        timings=[SimpleNamespace(stage="validate", seconds=0.01), SimpleNamespace(stage="ocr", seconds=2.5)],
    )


def test_expected_label_from_filename() -> None:
    assert C.expected_label("scam_kyc.png") == "scam"
    assert C.expected_label("SAFE-mom.jpg") == "safe"
    assert C.expected_label("IMG_2031.png") is None


def test_list_images_filters_and_sorts(tmp_path) -> None:
    for name in ["b.png", "a.JPG", "c.webp", "notes.txt", "README.md"]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    assert [p.name for p in C.list_images(tmp_path)] == ["a.JPG", "b.png", "c.webp"]
    assert C.list_images(tmp_path / "missing") == []


def test_check_image_prints_details_and_skips_llm_by_default(tmp_path, capsys) -> None:
    img = tmp_path / "scam_1.png"
    img.write_bytes(b"img")
    calls = []

    def fake_analyze(data, **kwargs):
        calls.append((data, kwargs))
        return _fake_result("Your KYC is pending")

    row = C.check_image(img, fake_analyze)
    assert calls == [(b"img", {"groq_api_key": "", "gemini_api_key": ""})]
    out = capsys.readouterr().out
    assert "Your KYC is pending" in out and "scam / high" in out
    assert (row.expected, row.verdict, row.ocr_seconds) == ("scam", "scam", 2.5)

    C.check_image(img, fake_analyze, use_llm=True)
    assert calls[-1][1] == {}


def test_check_image_reports_rejections_without_raising(tmp_path, capsys) -> None:
    img = tmp_path / "x.png"
    img.write_bytes(b"x")

    def bad_type(data, **kwargs):
        raise InvalidImageError("unsupported_type", "nope")

    def no_text(data, **kwargs):
        raise NoTextFoundError("empty")

    assert C.check_image(img, bad_type).verdict == "rejected:unsupported_type"
    assert C.check_image(img, no_text).verdict == "rejected:no_text"


def test_summary_table_contains_no_message_text(tmp_path) -> None:
    img = tmp_path / "safe_chat.png"
    img.write_bytes(b"x")
    row = C.check_image(img, lambda data, **kw: _fake_result("SECRET personal words", verdict="safe"))
    table = C.format_summary([row])
    assert "SECRET" not in table
    assert "| safe_chat.png | safe | safe | high | 0.91 | 0.80 | 2.5 |" in table


def test_main_with_empty_folder_returns_1_and_writes_nothing(tmp_path, capsys) -> None:
    assert C.main([str(tmp_path)]) == 1
    assert "No PNG/JPEG/WebP images" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
