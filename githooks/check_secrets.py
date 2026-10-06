#!/usr/bin/env python3
"""Block commits that contain API keys or secret files. Standard library only.

Run by the ``githooks/pre-commit`` shim (see README, "Git hooks"). It inspects the
*staged* version of every file being committed and refuses the commit if it finds

* a token that looks like a Groq, Hugging Face, Google/Gemini, Kaggle, GitHub,
  Anthropic/OpenAI-style or JWT (e.g. Supabase) key, or a private-key block; or
* a file that should never be committed (``.env``, ``kaggle.json``, keystores, ...).

Matched secret values are **never printed**: reports show only the file, line number
and the kind of secret, so the hook itself cannot leak what it finds.

A line containing ``secret-scan: allow`` is skipped (for test fixtures that must
contain something key-shaped).

Usage::

    python githooks/check_secrets.py          # scan staged files (what the hook runs)
    python githooks/check_secrets.py --all    # scan every file git would commit

Exit codes: 0 clean, 1 secrets found (commit blocked), 2 could not run.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import PurePosixPath

# Real tokens are long; the minimum lengths keep ordinary identifiers such as
# ``hf_phishing_texts`` or ``hf_hub_download`` from matching.
PATTERNS: dict[str, re.Pattern[str]] = {
    "Groq API key (gsk_)": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "Hugging Face token (hf_)": re.compile(r"hf_[A-Za-z0-9]{30,}"),
    "Google API key (AIza)": re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    "Gemini API key (AQ. form)": re.compile(r"AQ\.Ab[0-9A-Za-z_\-]{20,}"),
    "Kaggle token (KGAT_)": re.compile(r"KGAT_[A-Za-z0-9]{16,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "Anthropic/OpenAI-style key (sk-)": re.compile(r"(?<![A-Za-z0-9])sk-(?:ant-)?[A-Za-z0-9_\-]{30,}"),
    "JWT (e.g. Supabase key)": re.compile(
        r"eyJ[A-Za-z0-9_\-]{15,}\.eyJ[A-Za-z0-9_\-]{15,}\.[A-Za-z0-9_\-]{10,}"
    ),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY"),
}
ALLOW_MARKER = "secret-scan: allow"
MAX_BYTES = 5_000_000  # larger files are skipped (data/model files are gitignored anyway)

# File names that must never be committed, whatever they contain.
FORBIDDEN_NAMES = {"kaggle.json", "access_token.txt", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = (".pem", ".p12", ".jks", ".keystore")

Finding = tuple[str, int, str]  # (path, line number or 0 for whole-file, description)


def forbidden_filename(path: str) -> str | None:
    """Return why ``path`` may never be committed, or ``None`` if the name is fine."""
    name = PurePosixPath(path.replace("\\", "/")).name
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "environment file (holds real secrets)"
    if name in FORBIDDEN_NAMES:
        return f"credentials file ({name})"
    if name.endswith(FORBIDDEN_SUFFIXES):
        return "key / keystore file"
    return None


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, description)`` for every key-shaped string in ``text``.

    The matched value itself is deliberately not returned.
    """
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(line):
                hits.append((number, label))
    return hits


def scan_bytes(path: str, data: bytes) -> list[Finding]:
    """Scan one file's content (and its name). Binary and very large files are skipped."""
    findings: list[Finding] = []
    reason = forbidden_filename(path)
    if reason:
        findings.append((path, 0, reason))
    if len(data) > MAX_BYTES or b"\0" in data[:8192]:
        return findings
    findings += [(path, n, label) for n, label in scan_text(data.decode("utf-8", errors="replace"))]
    return findings


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def staged_files() -> list[str]:
    """Paths added/copied/modified/renamed in the index."""
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def all_files() -> list[str]:
    """Every file git would commit: tracked plus untracked-but-not-ignored."""
    out = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="scan every file git would commit, not just staged ones")
    args = parser.parse_args(argv)

    try:
        paths = all_files() if args.all else staged_files()
        findings: list[Finding] = []
        for path in paths:
            if args.all:
                try:
                    with open(path, "rb") as fh:
                        data = fh.read(MAX_BYTES + 1)
                except OSError:
                    continue
            else:
                data = _git("show", f":{path}")  # the staged content, not the working copy
            findings += scan_bytes(path, data)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"secret scan could not run: {type(exc).__name__}", file=sys.stderr)
        return 2

    if not findings:
        return 0
    print("Commit blocked: possible secrets found (values are never printed):", file=sys.stderr)
    for path, line, what in findings:
        where = f"{path}:{line}" if line else path
        print(f"  {where}  {what}", file=sys.stderr)
    print(
        "\nRemove the secret (keep real keys in the gitignored .env only) and stage the file again.\n"
        "If a match is a harmless fixture, add '# secret-scan: allow' to that line.\n"
        "If a key was ever committed or pasted somewhere public, rotate it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
