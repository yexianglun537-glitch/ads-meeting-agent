import importlib.util
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CORE_REQUIREMENTS = {
    "annotated-types==0.8.0",
    "anyio==4.14.2",
    "certifi==2026.7.22",
    "charset-normalizer==3.5.1",
    "click==8.5.0",
    "fastapi==0.116.1",
    "h11==0.16.0",
    "httpcore==1.0.9",
    "httpx==0.28.1",
    "idna==3.19",
    "pydantic==2.12.5",
    "pydantic-core==2.41.5",
    "python-dotenv==1.1.1",
    "python-multipart==0.0.20",
    "requests==2.32.5",
    "starlette==0.47.3",
    "typing-extensions==4.16.0",
    "typing-inspection==0.4.4",
    "urllib3==2.7.0",
    "uvicorn==0.35.0",
}


def test_source_core_dependencies_are_locked_for_offline_install():
    lines = (ROOT / "backend" / "requirements-core.txt").read_text(encoding="utf-8").splitlines()
    requirements = {line.strip() for line in lines if line.strip() and not line.startswith("#")}

    assert requirements == CORE_REQUIREMENTS
    assert all("[standard]" not in requirement for requirement in requirements)
    assert all(
        package not in requirement
        for package in ("faster-whisper", "sherpa-onnx", "numpy")
        for requirement in requirements
    )


def test_source_packager_builds_four_version_windows_wheelhouse():
    script = (ROOT / "packaging" / "build-source-package.ps1").read_text(encoding="utf-8")

    assert '"backend/requirements-core.txt"' in script
    assert "--only-binary=:all:" in script
    assert "--platform win_amd64" in script
    assert "--implementation cp" in script
    for version in ("311", "312", "313", "314"):
        assert f'Version = "{version}"; Abi = "cp{version}"' in script
    assert '@("pydantic_core", "charset_normalizer")' in script
    assert '"$package-*-$($target.Abi)-$($target.Abi)-win_amd64.whl"' in script
    assert "GetRelativePath($packageRoot, $item.FullName)" in script
    assert "$item.FullName -match" not in script


def test_source_packager_verifies_and_stages_prebuilt_frontend():
    script = (ROOT / "packaging" / "build-source-package.ps1").read_text(encoding="utf-8")

    assert 'Invoke-Checked "npm.cmd" @("test") $frontend' in script
    assert 'Invoke-Checked "npm.cmd" @("run", "typecheck") $frontend' in script
    assert 'Invoke-Checked "npm.cmd" @("run", "build") $frontend' in script
    assert 'Join-Path $frontendDist "index.html"' in script
    assert 'Copy-Item -LiteralPath $frontendDist -Destination (Join-Path $packageRoot "frontend\\dist") -Recurse' in script
    assert '$relativePath -notmatch "^frontend[\\\\/]dist([\\\\/]|$)"' in script
    assert '"node_modules"' in script


def test_source_cmd_bootstraps_supported_python_and_offline_dependencies():
    script = (ROOT / "start-dev.cmd").read_text(encoding="utf-8").lower()

    assert "py.exe" in script
    version_checks = [script.index(f"call :try_py {version}") for version in ("3.13", "3.12", "3.14", "3.11")]
    assert version_checks == sorted(version_checks)
    assert "struct.calcsize('p') * 8 == 64" in script
    assert "^<" not in script
    assert "--no-index" in script
    assert "--find-links" in script
    assert "requirements-core.txt" in script
    assert "-m pip check" in script
    assert "packaging\\launcher.py\" --lightweight --port 8000" in script
    assert "https://github.com/yexianglun537-glitch/ads-meeting-agent/releases" in script
    for runtime_dependency in ("npm", "node", "vite", "5173"):
        assert runtime_dependency not in script


def test_visible_batch_delegates_to_cmd_launcher():
    script = (ROOT / "启动项目.bat").read_text(encoding="utf-8").lower()

    assert 'call "%~dp0start-dev.cmd"' in script


def _load_launcher():
    spec = importlib.util.spec_from_file_location("ads_packaging_launcher", ROOT / "packaging" / "launcher.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lightweight_runtime_requires_only_frontend_and_finds_next_port(tmp_path, monkeypatch):
    launcher = _load_launcher()
    resources = tmp_path / "resources"
    frontend = resources / "frontend" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("ok", encoding="utf-8")
    monkeypatch.setattr(launcher, "application_root", lambda: tmp_path)

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        if port > 65525:
            pytest.skip("ephemeral port is too close to the maximum port")
        assert launcher.check_runtime(resources, port, lightweight=True) == port + 1


def test_full_runtime_keeps_strict_asset_checks(tmp_path, monkeypatch):
    launcher = _load_launcher()
    monkeypatch.setattr(launcher, "application_root", lambda: tmp_path)

    with pytest.raises(RuntimeError, match="发行包缺少必要文件"):
        launcher.check_runtime(tmp_path, 8000, lightweight=False)


def test_source_delivery_docs_match_lightweight_runtime_and_github_fallback():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "guides" / "ADS会议智能体使用教程.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    packager = (ROOT / "packaging" / "build-source-package.ps1").read_text(encoding="utf-8")
    fallback = "https://github.com/yexianglun537-glitch/ads-meeting-agent/releases"

    for document in (readme, guide):
        assert "Windows 10/11 x64" in document
        assert "Python 3.11–3.14" in document
        assert "启动项目.bat" in document
        assert "http://127.0.0.1:8000/" in document
        assert "8001–8010" in document
        assert "轻量源码包" in document
        assert "文字输入" in document
        assert fallback in document
    assert "不需要 Node.js" in readme
    assert "本地语音组件未随轻量源码包提供" in readme
    assert "需要 Python 3.11+、Node.js 20+" not in guide
    assert "前端：http://127.0.0.1:5173" not in guide
    assert "以下命令仅供开发维护人员" in guide
    assert "2026-08-31-源码包兼容性交付要求.md" in docs_index
    assert '"docs/README.md"' in packager
    assert '"docs/requirements/2026-08-31-源码包兼容性交付要求.md"' in packager
    assert '$zipPath = Join-Path $outputRoot "04- ADS会议智能体源代码.zip"' in packager
