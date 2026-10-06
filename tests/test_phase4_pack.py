"""Tests for the Colab data pack: no raw text, no leakage, no synthetic test rows."""
import zipfile

import pandas as pd
import pytest

from src.training import phase4_pack as P


def _frame(prefix: str, n: int = 6, synthetic: bool = False) -> pd.DataFrame:
    return pd.DataFrame({
        "id": [f"{prefix}{i}" for i in range(n)],
        "text": [f"{prefix} message number {i}" for i in range(n)],
        "text_raw": [f"RAW {prefix} message number {i} https://x.example" for i in range(n)],
        "urls": [[] for _ in range(n)],
        "label": ["scam" if i % 3 == 0 else "safe" for i in range(n)],
        "source": "uci_sms_spam", "is_synthetic": synthetic, "language": "en", "scam_type": "none",
        "subtype": "unspecified", "benchmark": False,
    })


@pytest.fixture()
def source_dir(tmp_path):
    d = tmp_path / "p4"
    d.mkdir()
    for name in P.SPLITS:
        _frame(name).to_parquet(d / f"{name}.parquet", index=False)
    return d


def test_slim_drops_raw_text_and_keeps_length():
    out = P.slim(_frame("a"))
    assert list(out.columns) == P.PACK_COLUMNS
    assert "text_raw" not in out and "urls" not in out
    assert out["raw_chars"].iloc[0] == len(_frame("a")["text_raw"].iloc[0])


def test_build_pack_writes_expected_files(source_dir, tmp_path):
    out = tmp_path / "pack.zip"
    summary = P.build_pack(source_dir, out, holdout_candidates=())
    assert not summary["real_indian_test_included"]
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == ["test.parquet", "train.parquet", "val.parquet"]
        zf.extract("train.parquet", tmp_path)
    assert "text_raw" not in pd.read_parquet(tmp_path / "train.parquet").columns


def test_holdout_is_included_when_present(source_dir, tmp_path):
    hold = _frame("hold").drop(columns=["benchmark"])
    path = tmp_path / "real_indian_test.parquet"
    hold.to_parquet(path, index=False)
    summary = P.build_pack(source_dir, tmp_path / "pack.zip", holdout_candidates=(path,))
    assert summary["files"]["real_indian_test"]["rows"] == 6


def test_synthetic_test_rows_are_rejected(source_dir, tmp_path):
    _frame("test", synthetic=True).to_parquet(source_dir / "test.parquet", index=False)
    with pytest.raises(ValueError, match="100% real"):
        P.build_pack(source_dir, tmp_path / "pack.zip", holdout_candidates=())


def test_id_overlap_between_splits_is_rejected(source_dir, tmp_path):
    val = _frame("val")
    val.loc[0, "id"] = "train0"
    val.to_parquet(source_dir / "val.parquet", index=False)
    with pytest.raises(ValueError, match="id overlap"):
        P.build_pack(source_dir, tmp_path / "pack.zip", holdout_candidates=())


def test_identical_text_across_splits_is_rejected(source_dir, tmp_path):
    test = _frame("test")
    test.loc[0, "text"] = "train message number 0"
    test.to_parquet(source_dir / "test.parquet", index=False)
    with pytest.raises(ValueError, match="identical text"):
        P.build_pack(source_dir, tmp_path / "pack.zip", holdout_candidates=())


def test_holdout_overlapping_training_text_is_rejected(source_dir, tmp_path):
    hold = _frame("hold")
    hold.loc[0, "text"] = "train message number 1"
    path = tmp_path / "h.parquet"
    hold.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="real Indian"):
        P.build_pack(source_dir, tmp_path / "pack.zip", holdout_candidates=(path,))
