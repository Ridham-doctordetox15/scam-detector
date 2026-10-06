"""Phase 0 smoke tests: the project skeleton exists and packages import."""
from importlib import import_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PACKAGES = [
    "src",
    "src.preprocessing",
    "src.training",
    "src.inference",
    "src.rag",
    "src.llm",
    "src.ocr",
    "src.url_analyzer",
    "api",
]

DIRECTORIES = [
    "data/raw",
    "data/processed",
    "data/synthetic",
    "notebooks",
    "web",
    "mobile",
    "docs",
    "tests",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name: str) -> None:
    """Every package in the skeleton is importable."""
    assert import_module(name) is not None


@pytest.mark.parametrize("rel_path", DIRECTORIES)
def test_directory_exists(rel_path: str) -> None:
    """Every folder required by the project layout exists."""
    assert (ROOT / rel_path).is_dir()


def test_env_example_lists_required_keys() -> None:
    """.env.example documents every secret the project expects."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "HF_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"):
        assert f"{key}=" in text


# --------------------------------------------------------------------------- #
# Secret hygiene: .env.example is committed, so it may only hold placeholders.
# Failure messages name the variables and never include their values.
# --------------------------------------------------------------------------- #
import re  # noqa: E402

_PLACEHOLDER_RE = re.compile(r"^your_[a-z0-9_]+_here$")
_ALLOWED_PLACEHOLDER_VALUES = {"", "https://your-project-ref.supabase.co"}


def non_placeholder_keys(text: str) -> list[str]:
    """Names of variables in ``.env``-style ``text`` whose value is not a placeholder."""
    offenders: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        value = value.strip().strip("'\"")
        if value in _ALLOWED_PLACEHOLDER_VALUES or _PLACEHOLDER_RE.match(value):
            continue
        offenders.append(name.strip())
    return offenders


def test_env_example_contains_only_placeholders() -> None:
    """A real key in .env.example would be committed; keep real keys in .env only."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    offenders = non_placeholder_keys(text)
    assert not offenders, f".env.example has non-placeholder value(s) for: {offenders}"


def test_env_example_has_no_key_shaped_strings() -> None:
    """Independent of the placeholder rule: no token-like text anywhere in the file."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_secrets", ROOT / "githooks" / "check_secrets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hits = module.scan_text((ROOT / ".env.example").read_text(encoding="utf-8"))
    assert not hits, f".env.example contains key-shaped strings at lines: {[n for n, _ in hits]}"


def test_placeholder_detector_catches_real_looking_values() -> None:
    fake = "".join(["gsk_", "x1Y2" * 10])
    text = f"GROQ_API_KEY={fake}\nHF_TOKEN=your_huggingface_token_here\nSUPABASE_KEY=\n# NOTE=anything\n"
    assert non_placeholder_keys(text) == ["GROQ_API_KEY"]
    assert non_placeholder_keys("A=your_x_here\nB=\nC='your_y_here'\n") == []
    assert non_placeholder_keys("SUPABASE_URL=https://abcdefgh.supabase.co\n") == ["SUPABASE_URL"]


def test_dotenv_is_gitignored() -> None:
    lines = {ln.strip() for ln in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert ".env" in lines
    assert "!.env.example" in lines
