"""Tests for src.preprocessing.schema."""
import pytest

from src.preprocessing.schema import (
    COLUMNS,
    empty_frame,
    make_frame,
    validate_frame,
)


def test_make_frame_defaults_scam_type_by_label() -> None:
    df = make_frame(["a", "b"], ["scam", "safe"], source="s")
    assert list(df.columns) == COLUMNS
    assert df["scam_type"].tolist() == ["unknown", "none"]
    assert df["language"].tolist() == ["en", "en"]
    assert not df["is_synthetic"].any()
    assert df["generator"].isna().all()


def test_make_frame_accepts_per_row_values() -> None:
    df = make_frame(
        ["a", "b"], ["scam", "safe"], source="s", scam_type=["lottery", "none"],
        language=["hi", "en"], is_synthetic=True, generator=["groq/x", "gemini/y"],
    )
    assert df["scam_type"].tolist() == ["lottery", "none"]
    assert df["is_synthetic"].all()
    assert df["generator"].tolist() == ["groq/x", "gemini/y"]


def test_validate_accepts_valid_and_empty_frames() -> None:
    validate_frame(make_frame(["hello"], ["safe"], source="s"))
    validate_frame(empty_frame())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"texts": ["x"], "labels": ["spam"]},                              # bad label
        {"texts": ["x"], "labels": ["scam"], "scam_type": "made_up"},      # bad scam_type
        {"texts": ["  "], "labels": ["scam"]},                             # blank text
    ],
)
def test_validate_rejects_bad_rows(kwargs: dict) -> None:
    df = make_frame(kwargs.pop("texts"), kwargs.pop("labels"), source="s", **kwargs)
    with pytest.raises(ValueError):
        validate_frame(df)


def test_validate_rejects_wrong_columns() -> None:
    df = make_frame(["x"], ["scam"], source="s").drop(columns="generator")
    with pytest.raises(ValueError, match="columns"):
        validate_frame(df)
