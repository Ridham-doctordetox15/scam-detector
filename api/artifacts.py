"""Fetch and verify the gitignored model artifacts the API needs.

The only trained artifact the deployed API loads is the TF-IDF + Linear SVM
bundle (``models/baseline_phase4/svm.joblib``, ~11 MB). It lives in a
**private Hugging Face model repo** and is downloaded at build time with an
``HF_TOKEN`` secret. Its SHA-256 is pinned in ``api/artifacts.lock.json``
(committed), and the file is verified after download *and* before loading:
a ``.joblib`` file is a pickle, and unpickling an unexpected file can run
arbitrary code, so an unverified file is never loaded.

The knowledge base (``data/knowledge_base/scam_patterns.json``) is tracked in
git and needs no download; the RAG index is rebuilt from it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

LOCK_PATH = Path(__file__).with_name("artifacts.lock.json")


class ArtifactError(RuntimeError):
    """An artifact is missing, unverifiable or its hash does not match the lock file."""


@dataclass(frozen=True)
class Artifact:
    repo_filename: str   # path inside the model repo
    local_path: Path     # where the app loads it from
    sha256: str


def load_lock(path: Path = LOCK_PATH) -> list[Artifact]:
    """Artifacts pinned in the lock file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Artifact(a["repo_filename"], Path(a["local_path"]), a["sha256"].lower()) for a in data["artifacts"]]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(artifact: Artifact, root: Path = Path(".")) -> None:
    """Raise :class:`ArtifactError` unless the local file exists and matches its pinned hash."""
    path = root / artifact.local_path
    if not path.is_file():
        raise ArtifactError(f"missing artifact: {artifact.local_path}")
    actual = sha256_file(path)
    if actual != artifact.sha256:
        raise ArtifactError(f"SHA-256 mismatch for {artifact.local_path}: expected {artifact.sha256[:12]}..., "
                            f"got {actual[:12]}...")


def verify_all(root: Path = Path("."), lock_path: Path = LOCK_PATH) -> None:
    for artifact in load_lock(lock_path):
        verify(artifact, root)


def read_token() -> str | None:
    """HF token from ``HF_TOKEN``, or from the file named by ``HF_TOKEN_FILE`` (Docker build secret)."""
    token = os.getenv("HF_TOKEN", "").strip()
    if token:
        return token
    token_file = os.getenv("HF_TOKEN_FILE", "").strip()
    if token_file and Path(token_file).is_file():
        return Path(token_file).read_text(encoding="utf-8").strip() or None
    return None


def fetch_all(repo_id: str, revision: str = "main", token: str | None = None, root: Path = Path("."),
              lock_path: Path = LOCK_PATH, downloader=None) -> list[Path]:
    """Download every locked artifact from ``repo_id`` (a model repo) and verify it.

    Files already present with the right hash are not downloaded again. A
    downloaded file is only moved into place after its hash matches.

    Raises:
        ArtifactError: Download failed, or a hash does not match.
    """
    if downloader is None:
        from huggingface_hub import hf_hub_download as downloader  # noqa: N813
    placed = []
    for artifact in load_lock(lock_path):
        target = root / artifact.local_path
        if target.is_file() and sha256_file(target) == artifact.sha256:
            placed.append(target)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            try:
                downloaded = Path(downloader(repo_id=repo_id, filename=artifact.repo_filename, revision=revision,
                                             token=token, local_dir=tmp))
            except Exception as exc:  # network/auth/404 - never include the token
                raise ArtifactError(f"could not download {artifact.repo_filename} from {repo_id}@{revision} "
                                    f"({type(exc).__name__})") from None
            actual = sha256_file(downloaded)
            if actual != artifact.sha256:
                raise ArtifactError(f"SHA-256 mismatch for downloaded {artifact.repo_filename}: expected "
                                    f"{artifact.sha256[:12]}..., got {actual[:12]}... (refusing to install it)")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(downloaded), target)
        placed.append(target)
    return placed
