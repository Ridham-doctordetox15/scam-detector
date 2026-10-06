"""Tests for deployment helpers: artifact pinning/fetch, prefetch, Space staging, service loading."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from api import artifacts, prefetch, stage_space
from api.config import Settings
from api.services import Component, NoMatchRag, Services

ROOT = Path(__file__).resolve().parents[1]


def _lock(tmp_path: Path, content: bytes, local: str = "models/m/svm.joblib") -> Path:
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"artifacts": [{"repo_filename": "svm.joblib", "local_path": local,
                                               "sha256": hashlib.sha256(content).hexdigest()}]}))
    return lock


def _downloader(content: bytes, calls: list | None = None):
    def download(repo_id, filename, revision, token, local_dir):
        if calls is not None:
            calls.append((repo_id, filename, revision, token))
        path = Path(local_dir) / filename
        path.write_bytes(content)
        return str(path)
    return download


# ------------------------------------------------------------------ artifacts
def test_committed_lock_matches_local_model_if_present() -> None:
    lock = artifacts.load_lock()
    assert len(lock) == 1 and lock[0].repo_filename == "svm.joblib" and len(lock[0].sha256) == 64
    path = ROOT / lock[0].local_path
    if not path.exists():
        pytest.skip("trained model not present (gitignored)")
    artifacts.verify(lock[0], ROOT)


def test_fetch_downloads_verifies_and_places(tmp_path) -> None:
    content = b"model-bytes"
    calls: list = []
    placed = artifacts.fetch_all("me/models", "abc123", token="t", root=tmp_path,
                                 lock_path=_lock(tmp_path, content), downloader=_downloader(content, calls))
    assert placed == [tmp_path / "models/m/svm.joblib"] and placed[0].read_bytes() == content
    assert calls == [("me/models", "svm.joblib", "abc123", "t")]


def test_fetch_skips_download_when_file_already_verified(tmp_path) -> None:
    content = b"model-bytes"
    lock = _lock(tmp_path, content)
    (tmp_path / "models/m").mkdir(parents=True)
    (tmp_path / "models/m/svm.joblib").write_bytes(content)
    calls: list = []
    artifacts.fetch_all("me/models", root=tmp_path, lock_path=lock, downloader=_downloader(content, calls))
    assert calls == []


def test_fetch_refuses_hash_mismatch_and_installs_nothing(tmp_path) -> None:
    lock = _lock(tmp_path, b"expected")
    with pytest.raises(artifacts.ArtifactError, match="mismatch"):
        artifacts.fetch_all("me/models", root=tmp_path, lock_path=lock, downloader=_downloader(b"tampered"))
    assert not (tmp_path / "models/m/svm.joblib").exists()


def test_fetch_download_error_never_contains_token(tmp_path) -> None:
    def failing(**kwargs):
        raise RuntimeError(f"401 for token {kwargs['token']}")

    with pytest.raises(artifacts.ArtifactError) as exc:
        artifacts.fetch_all("me/models", token="hf_SUPERSECRETVALUE", root=tmp_path,
                            lock_path=_lock(tmp_path, b"x"), downloader=lambda **kw: failing(**kw))
    assert "SUPERSECRETVALUE" not in str(exc.value) and "RuntimeError" in str(exc.value)


def test_verify_missing_and_mismatch(tmp_path) -> None:
    art = artifacts.Artifact("svm.joblib", Path("a.joblib"), hashlib.sha256(b"a").hexdigest())
    with pytest.raises(artifacts.ArtifactError, match="missing"):
        artifacts.verify(art, tmp_path)
    (tmp_path / "a.joblib").write_bytes(b"b")
    with pytest.raises(artifacts.ArtifactError, match="mismatch"):
        artifacts.verify(art, tmp_path)


def test_read_token_env_then_file(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN_FILE", raising=False)
    assert artifacts.read_token() is None
    secret_file = tmp_path / "HF_TOKEN"
    secret_file.write_text("from-file\n")
    monkeypatch.setenv("HF_TOKEN_FILE", str(secret_file))
    assert artifacts.read_token() == "from-file"
    monkeypatch.setenv("HF_TOKEN", "from-env")
    assert artifacts.read_token() == "from-env"


# ------------------------------------------------------------------ prefetch
def test_prefetch_required_failure_sets_exit_code(monkeypatch, capsys) -> None:
    monkeypatch.setattr(prefetch, "fetch_model", lambda: (_ for _ in ()).throw(artifacts.ArtifactError("nope")))
    monkeypatch.setattr(prefetch, "fetch_openphish", lambda: (_ for _ in ()).throw(OSError("offline")))
    assert prefetch.run(["model"]) == 1
    assert prefetch.run(["openphish"]) == 0  # optional step
    out = capsys.readouterr().out
    assert "model: FAILED" in out and "openphish: skipped (optional)" in out


def test_prefetch_model_requires_repo_id_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(artifacts, "verify_all", lambda: (_ for _ in ()).throw(artifacts.ArtifactError("missing")))
    monkeypatch.delenv("MODEL_REPO_ID", raising=False)
    with pytest.raises(artifacts.ArtifactError, match="MODEL_REPO_ID"):
        prefetch.fetch_model()


def test_prefetch_model_uses_env_repo(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(artifacts, "verify_all", lambda: (_ for _ in ()).throw(artifacts.ArtifactError("missing")))
    monkeypatch.setattr(artifacts, "fetch_all", lambda repo, revision, token: seen.update(r=repo, v=revision))
    monkeypatch.setenv("MODEL_REPO_ID", "me/scam-detector-models")
    monkeypatch.setenv("MODEL_REPO_REVISION", "")
    assert "me/scam-detector-models@main" in prefetch.fetch_model()
    assert seen == {"r": "me/scam-detector-models", "v": "main"}


def test_prefetch_rejects_unknown_step() -> None:
    with pytest.raises(SystemExit):
        prefetch.main(["--steps", "model,bogus"])


# ------------------------------------------------------------------ staging
def test_stage_docker_allowlist_and_no_secrets(tmp_path) -> None:
    out = tmp_path / "space"
    files = {p.relative_to(out).as_posix() for p in stage_space.stage("docker", out)}
    assert {"Dockerfile", ".dockerignore", "requirements-api.txt", "README.md", "api/main.py",
            "api/artifacts.lock.json", "src/pipeline.py", "data/knowledge_base/scam_patterns.json"} <= files
    assert not any(f.startswith(("models/", "notebooks/", "tests/")) or f.endswith((".env", ".joblib", ".csv"))
                   for f in files)
    assert not any("__pycache__" in f for f in files)
    assert (out / "README.md").read_text(encoding="utf-8").startswith("---\ntitle:")
    assert "sdk: docker" in (out / "README.md").read_text(encoding="utf-8")


def test_stage_gradio_requires_sdk_version_and_builds_requirements(tmp_path) -> None:
    with pytest.raises(ValueError, match="sdk-version"):
        stage_space.stage("gradio", tmp_path / "g")
    out = tmp_path / "g2"
    files = {p.relative_to(out).as_posix() for p in stage_space.stage("gradio", out, "5.0.0")}
    assert {"app.py", "requirements.txt", "README.md"} <= files and "Dockerfile" not in files
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "sdk_version: 5.0.0" in readme and "{SDK_VERSION}" not in readme


def test_gradio_requirements_transform() -> None:
    reqs = stage_space.gradio_requirements("# c\nfastapi==1\ntorch==2.14.0+cpu\nscikit-learn==1.9.1  # pin\n\n")
    lines = [ln for ln in reqs.splitlines() if not ln.startswith("#")]
    assert lines == ["torch", "scikit-learn==1.9.1", "spaces"]


def test_stage_refuses_to_delete_foreign_folder(tmp_path) -> None:
    out = tmp_path / "mine"
    out.mkdir()
    (out / "keep.txt").write_text("user data")
    with pytest.raises(FileExistsError):
        stage_space.stage("docker", out)
    assert (out / "keep.txt").exists()


def test_stage_aborts_on_secret(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(stage_space, "scan_for_secrets", lambda folder: [("api/x.py", 3, "Groq API key (gsk_)")])
    out = tmp_path / "s"
    with pytest.raises(RuntimeError, match="secret scan failed"):
        stage_space.stage("docker", out)
    assert not out.exists()


def test_secret_scanner_detects_key_in_staged_folder(tmp_path) -> None:
    (tmp_path / "leak.py").write_text('KEY = "gsk_' + "a1B2c3D4" * 5 + '"\n')  # secret-scan: allow
    findings = stage_space.scan_for_secrets(tmp_path)
    assert findings and findings[0][0] == "leak.py" and "gsk_" in findings[0][2]


def test_dockerfile_essentials() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "useradd -m -u 1000 user" in text and "EXPOSE 7860" in text
    assert "--mount=type=secret,id=HF_TOKEN" in text and "python -m api.prefetch" in text
    assert '"--workers", "1"' in text and "--no-access-log" in text
    assert "EASYOCR_DOWNLOAD_ENABLED=0" in text and "HF_HUB_OFFLINE=1" in text
    assert "ENV HF_TOKEN" not in text  # the token must never become an image ENV
    assert "COPY . " not in text and "COPY --chown=user . " not in text  # allowlisted copies only


def test_dockerignore_excludes_secrets_and_data() -> None:
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert lines[1] == "*" or "*" in lines
    assert "**/.env" in lines and "!data/knowledge_base/scam_patterns.json" in lines


# ------------------------------------------------------------------ service loading
def test_load_all_isolates_component_failures(monkeypatch) -> None:
    svc = Services(Settings(load_models=True, warmup=False))

    def ok_classifier():
        svc.predictor, svc.classifier_model = object(), "tfidf_svm"
        svc.components["classifier"] = Component(True, "tfidf_svm")

    monkeypatch.setattr(svc, "_load_classifier", ok_classifier)
    monkeypatch.setattr(svc, "_load_url_analyzer", lambda: None)
    monkeypatch.setattr(svc, "_load_rag", lambda: (_ for _ in ()).throw(OSError("no index")))
    monkeypatch.setattr(svc, "_load_ocr", lambda: (_ for _ in ()).throw(MemoryError()))
    svc.load_all()
    assert svc.components["classifier"].ready
    assert svc.components["rag"] == Component(False, "failed to load (OSError)")
    assert svc.components["ocr"] == Component(False, "failed to load (MemoryError)")
    assert svc.status() == "degraded"


def test_classifier_refuses_unverified_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(artifacts, "verify_all", lambda: (_ for _ in ()).throw(artifacts.ArtifactError("mismatch")))
    svc = Services(Settings(verify_artifacts=True))
    with pytest.raises(artifacts.ArtifactError):
        svc._load_classifier()
    assert svc.predictor is None and svc.status() == "unavailable"


@pytest.mark.skipif(not (ROOT / "models/baseline_phase4/svm.joblib").exists(), reason="trained model not present")
def test_real_classifier_loads_with_verification(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    svc = Services(Settings())
    svc._load_classifier()
    assert svc.classifier_model == "tfidf_svm" and svc.components["classifier"].ready


def test_no_match_rag() -> None:
    result = NoMatchRag().retrieve("anything")
    assert result.matches == [] and result.confident is False


# ------------------------------------------------------------------ Gradio/ZeroGPU adapter
@pytest.fixture(autouse=True)
def _restore_adapter_env(monkeypatch):
    # The adapter sets defaults with os.environ.setdefault on import; register them for restore.
    for key in ("TRUSTED_PROXY_HOPS", "LOAD_DOTENV", "ANONYMIZED_TELEMETRY", "EASYOCR_DOWNLOAD_ENABLED"):
        monkeypatch.delenv(key, raising=False)


def _load_adapter():
    import importlib.util

    spec = importlib.util.spec_from_file_location("space_app", ROOT / "deploy/hf_space_gradio/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gradio_adapter_imports_without_side_effects(monkeypatch) -> None:
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    module = _load_adapter()  # must not start a server or download anything on import
    assert callable(module.main)
    import os
    assert os.environ["TRUSTED_PROXY_HOPS"] == "1" and os.environ["LOAD_DOTENV"] == "0"


def test_gradio_adapter_exits_when_prefetch_fails(monkeypatch) -> None:
    module = _load_adapter()
    started = []
    monkeypatch.setattr(prefetch, "run", lambda steps: 1)
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(1))
    with pytest.raises(SystemExit):
        module.main()
    assert started == []


def test_gradio_adapter_launches_factory_app(monkeypatch) -> None:
    module = _load_adapter()
    calls = []
    monkeypatch.setattr(prefetch, "run", lambda steps: 0)
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setenv("EASYOCR_DOWNLOAD_ENABLED", "1")
    module.main()
    app, kw = calls[0]
    assert app == "api.main:create_app" and kw["factory"] and kw["port"] == 7860 and kw["workers"] == 1
    assert kw["access_log"] is False
    import os
    assert os.environ["EASYOCR_DOWNLOAD_ENABLED"] == "0"
