"""Tests for the UCI, Hugging Face and Kaggle loaders (no network access)."""
import io
import json
import sys
import types
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from src.preprocessing import load_hf_phishing, load_kaggle, load_uci
from src.preprocessing.schema import COLUMNS

UCI_TEXT = (
    "ham\tGo until jurong point, crazy..\n"
    "spam\tFree entry in 2 a wkly comp to win FA Cup tickets\n"
    "bogus\tunknown label line\n"
    "ham\t\n"                      # empty text
    "no tab separator here\n"
    "ham\tOk lar... Joking wif u oni...\r\n"
)


def _uci_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SMSSpamCollection", UCI_TEXT)
        zf.writestr("readme", "ignored")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


# ------------------------------- UCI --------------------------------------- #
def test_parse_uci_maps_labels_and_skips_bad_lines(tmp_path: Path) -> None:
    path = tmp_path / "SMSSpamCollection"
    path.write_text(UCI_TEXT, encoding="utf-8")
    df = load_uci.parse_uci(path)
    assert list(df.columns) == COLUMNS
    assert len(df) == 3
    spam = df[df["label"] == "scam"].iloc[0]
    assert spam["scam_type"] == "generic_spam"
    assert set(df[df["label"] == "safe"]["scam_type"]) == {"none"}
    assert set(df["source"]) == {"uci_sms_spam"}
    assert not df["is_synthetic"].any()


def test_download_uci_extracts_and_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: int) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(_uci_zip_bytes())

    monkeypatch.setattr(load_uci.requests, "get", fake_get)
    path = load_uci.download_uci(tmp_path / "uci")
    assert path.read_text(encoding="utf-8").startswith("ham\tGo until")
    load_uci.download_uci(tmp_path / "uci")        # cached: no second request
    assert len(calls) == 1
    load_uci.download_uci(tmp_path / "uci", force=True)
    assert len(calls) == 2


def test_load_uci_without_download_reads_local_file(tmp_path: Path) -> None:
    (tmp_path / "SMSSpamCollection").write_text(UCI_TEXT, encoding="utf-8")
    assert len(load_uci.load_uci(tmp_path, download=False)) == 3


# ------------------------------ HF phishing -------------------------------- #
def test_parse_hf_phishing_maps_labels_and_skips_invalid(tmp_path: Path) -> None:
    records = [
        {"text": "Win a prize now", "label": 1},
        {"text": "See you at 5pm", "label": 0},
        {"text": "   ", "label": 1},              # blank
        {"text": None, "label": 0},               # missing text
        {"text": "weird label", "label": 2},      # bad label
        {"text": "no label"},
    ]
    path = tmp_path / "texts.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    df = load_hf_phishing.parse_hf_phishing(path)
    assert df["label"].tolist() == ["scam", "safe"]
    assert df["scam_type"].tolist() == ["unknown", "none"]
    assert set(df["source"]) == {"hf_phishing_texts"}


def test_download_hf_phishing_uses_hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake_download(**kwargs: object) -> str:
        seen.update(kwargs)
        return str(tmp_path / "texts.json")

    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    path = load_hf_phishing.download_hf_phishing(tmp_path, token="tok")
    assert path == tmp_path / "texts.json"
    assert seen["repo_id"] == "ealvaradob/phishing-dataset"
    assert seen["filename"] == "texts.json"
    assert seen["repo_type"] == "dataset"
    assert seen["token"] == "tok"


# -------------------------------- Kaggle ----------------------------------- #
SPEC = load_kaggle.KAGGLE_SPECS["subhajournal_phishingemails"]


def _write_kaggle_csv(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    csv = dest / SPEC.filename
    pd.DataFrame(
        {
            "Unnamed: 0": range(6),
            "Email Text": ["Click here to claim", "Meeting notes attached", None, "Odd label",
                           "  Padded  ", "   "],   # None and whitespace-only bodies exist in real data
            "Email Type": ["Phishing Email", "Safe Email", "Safe Email", "Mystery", "Safe Email",
                           "Phishing Email"],
        }
    ).to_csv(csv, index=False)
    return csv


def test_parse_kaggle_uses_spec_and_skips_bad_rows(tmp_path: Path) -> None:
    csv = _write_kaggle_csv(tmp_path)
    df = load_kaggle.parse_kaggle(csv, SPEC)
    assert df["label"].tolist() == ["scam", "safe", "safe"]
    assert set(df["source"]) == {SPEC.source}


def test_registry_is_extendable(tmp_path: Path) -> None:
    csv = tmp_path / "other.csv"
    pd.DataFrame({"body": ["x", "y"], "is_spam": ["1", "0"]}).to_csv(csv, index=False)
    spec = load_kaggle.KaggleSpec(
        slug="a/b", filename="other.csv", text_col="body", label_col="is_spam",
        label_map={"1": "scam", "0": "safe"}, source="kaggle_other",
    )
    assert load_kaggle.parse_kaggle(csv, spec)["label"].tolist() == ["scam", "safe"]
    assert spec.dirname == "a_b"


def test_download_kaggle_skips_when_present(tmp_path: Path) -> None:
    csv = _write_kaggle_csv(tmp_path / SPEC.dirname)
    assert load_kaggle.download_kaggle(SPEC, tmp_path) == csv


def test_download_kaggle_calls_api_and_checks_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    class FakeApi:
        def authenticate(self) -> None:
            calls.append("auth")

        def dataset_download_files(self, slug: str, path: str, unzip: bool, quiet: bool) -> None:
            calls.append(slug)
            _write_kaggle_csv(Path(path))

    monkeypatch.setitem(sys.modules, "kaggle", types.SimpleNamespace(api=FakeApi()))
    csv = load_kaggle.download_kaggle(SPEC, tmp_path)
    assert csv.exists()
    assert calls == ["auth", SPEC.slug]


def test_download_kaggle_raises_if_expected_csv_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class EmptyApi:
        def authenticate(self) -> None: ...
        def dataset_download_files(self, slug: str, path: str, unzip: bool, quiet: bool) -> None: ...

    monkeypatch.setitem(sys.modules, "kaggle", types.SimpleNamespace(api=EmptyApi()))
    with pytest.raises(FileNotFoundError):
        load_kaggle.download_kaggle(SPEC, tmp_path)
