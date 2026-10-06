"""Tests for githooks/check_secrets.py and its pre-commit shim.

Fake keys are assembled at runtime so this file contains nothing key-shaped and never
trips the hook itself.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_secrets", ROOT / "githooks" / "check_secrets.py")
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)

GIT = shutil.which("git")


def fake(prefix: str, n: int = 40) -> str:
    """A key-shaped string: ``prefix`` plus ``n`` mixed alphanumerics."""
    return prefix + ("aB3xY9" * 10)[:n]


KEYS = {
    "Groq": fake("gsk_"),
    "Hugging Face": fake("hf_"),
    "Google": fake("AIza"),
    "Gemini (AQ.": fake("AQ.Ab", 30),
    "Kaggle": fake("KGAT_", 32),
    "GitHub": fake("ghp_"),
    "Anthropic/OpenAI": fake("sk-ant-"),
    "JWT": "eyJ" + "a" * 20 + ".eyJ" + "b" * 20 + "." + "c" * 20,
    "Private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
}


# ------------------------------- pattern tests ----------------------------- #
@pytest.mark.parametrize("label, key", list(KEYS.items()))
def test_each_key_type_is_detected(label: str, key: str) -> None:
    hits = cs.scan_text(f"token = {key}\n")
    assert hits and hits[0][0] == 1
    assert label.split(" ")[0].lower() in hits[0][1].lower() or label.startswith(("JWT", "Private", "Gemini"))


def test_line_numbers_are_reported() -> None:
    text = "line one\nline two\nkey = " + KEYS["Groq"] + "\nlast\n"
    assert [n for n, _ in cs.scan_text(text)] == [3]


@pytest.mark.parametrize(
    "text",
    [
        "source = 'hf_phishing_texts'",
        "from huggingface_hub import hf_hub_download",
        "GROQ_API_KEY=your_groq_api_key_here",
        "HF_TOKEN=your_huggingface_token_here",
        "KAGGLE_API_TOKEN=your_kaggle_api_token_here",
        "SUPABASE_URL=https://your-project-ref.supabase.co",
        "a risk-averse-and-conservative-portfolio-allocation-strategy-for-all",
        "short gsk_abc and hf_abc and KGAT_abc and AIzaShort",
        "the task-force-of-many-different-people-working-on-things-together-daily",
        "plain prose with nothing secret in it",
    ],
)
def test_no_false_positives_on_ordinary_text(text: str) -> None:
    assert cs.scan_text(text) == []


def test_allow_marker_skips_a_line() -> None:
    line = f"x = '{KEYS['Groq']}'  # secret-scan: allow"
    assert cs.scan_text(line) == []
    assert cs.scan_text(line.replace("secret-scan: allow", "nothing")) != []


def test_scan_results_never_contain_the_secret() -> None:
    secret = KEYS["Groq"]
    findings = cs.scan_bytes("a.py", f"x = '{secret}'".encode())
    assert findings and secret not in repr(findings)


# ----------------------------- filename rules ------------------------------ #
@pytest.mark.parametrize(
    "path",
    [".env", ".env.local", ".env.production", "sub/dir/.env", "kaggle.json", "x/access_token.txt",
     "key.pem", "upload.jks", "release.keystore", "id_rsa", "C:\\repo\\.env"],
)
def test_forbidden_filenames(path: str) -> None:
    assert cs.forbidden_filename(path)


@pytest.mark.parametrize("path", [".env.example", "docs/.env.example", "env.py", "src/environment.py", "README.md"])
def test_allowed_filenames(path: str) -> None:
    assert cs.forbidden_filename(path) is None


def test_scan_bytes_flags_forbidden_name_even_for_binary_content() -> None:
    findings = cs.scan_bytes("upload.jks", b"\0\x01\x02binary")
    assert findings == [("upload.jks", 0, "key / keystore file")]


def test_binary_and_huge_files_are_skipped() -> None:
    assert cs.scan_bytes("data.bin", b"\0" + KEYS["Groq"].encode()) == []
    assert cs.scan_bytes("big.txt", KEYS["Groq"].encode() + b" " * (cs.MAX_BYTES + 1)) == []


# ------------------- integration: a real (temporary) git repo -------------- #
def run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    if GIT is None:
        pytest.skip("git is not installed")
    run(["git", "init", "-q"], tmp_path)
    return tmp_path


def scan(repo: Path, *flags: str) -> subprocess.CompletedProcess:
    return run([sys.executable, str(ROOT / "githooks" / "check_secrets.py"), *flags], repo)


def stage(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    run(["git", "add", name], repo)


def test_staged_secret_blocks_and_output_hides_it(repo: Path) -> None:
    stage(repo, "config.py", f"KEY = '{KEYS['Groq']}'\n")
    result = scan(repo)
    assert result.returncode == 1
    assert "config.py:1" in result.stderr and "Groq" in result.stderr
    assert KEYS["Groq"] not in result.stderr + result.stdout


def test_clean_staged_files_pass(repo: Path) -> None:
    stage(repo, "ok.py", "print('hello')\n")
    stage(repo, ".env.example", "GROQ_API_KEY=your_groq_api_key_here\n")
    assert scan(repo).returncode == 0


def test_staged_env_file_is_blocked_by_name(repo: Path) -> None:
    stage(repo, ".env", "SOMETHING=harmless\n")
    result = scan(repo)
    assert result.returncode == 1 and ".env" in result.stderr


def test_scanner_checks_the_staged_content_not_the_working_copy(repo: Path) -> None:
    stage(repo, "a.py", f"KEY = '{KEYS['Hugging Face']}'\n")
    (repo / "a.py").write_text("KEY = 'removed'\n", encoding="utf-8")        # cleaned but not re-staged
    assert scan(repo).returncode == 1
    run(["git", "add", "a.py"], repo)
    assert scan(repo).returncode == 0
    (repo / "a.py").write_text(f"KEY = '{KEYS['Hugging Face']}'\n", encoding="utf-8")   # dirty, unstaged
    assert scan(repo).returncode == 0


def test_all_flag_scans_untracked_files_but_respects_gitignore(repo: Path) -> None:
    (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (repo / "ignored.txt").write_text(KEYS["Kaggle"], encoding="utf-8")
    assert scan(repo, "--all").returncode == 0
    (repo / "notes.txt").write_text(f"token: {KEYS['Kaggle']}\n", encoding="utf-8")
    result = scan(repo, "--all")
    assert result.returncode == 1 and "notes.txt:1" in result.stderr and "ignored.txt" not in result.stderr


def test_scanner_outside_a_git_repo_fails_closed(tmp_path: Path) -> None:
    result = run([sys.executable, str(ROOT / "githooks" / "check_secrets.py")], tmp_path)
    assert result.returncode == 2 and "could not run" in result.stderr


def test_shim_uses_lf_line_endings() -> None:
    assert b"\r" not in (ROOT / "githooks" / "pre-commit").read_bytes()
    assert (ROOT / "githooks" / "pre-commit").read_bytes().startswith(b"#!/bin/sh\n")


@pytest.mark.skipif(GIT is None, reason="needs git (Git for Windows bundles its own sh for hooks)")
def test_real_commit_is_blocked_through_the_shim(repo: Path) -> None:
    shutil.copytree(ROOT / "githooks", repo / "githooks")
    run(["git", "config", "core.hooksPath", "githooks"], repo)
    env = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
    ident = ["-c", "user.name=t", "-c", "user.email=t@example.com"]

    stage(repo, "leak.py", f"KEY = '{KEYS['Groq']}'\n")
    blocked = run(["git", *ident, "commit", "-m", "leak"], repo, env)
    assert blocked.returncode != 0
    assert "Commit blocked" in blocked.stderr and KEYS["Groq"] not in blocked.stderr + blocked.stdout

    run(["git", "rm", "-q", "--cached", "leak.py"], repo)
    stage(repo, "fine.py", "x = 1\n")
    allowed = run(["git", *ident, "commit", "-m", "fine", "--", "fine.py"], repo, env)
    assert allowed.returncode == 0, allowed.stderr
