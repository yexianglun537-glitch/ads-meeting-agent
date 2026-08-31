from __future__ import annotations

import json
import struct
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = ROOT / "backend" / "data" / "speech_setup_status.json"
ACTIVE_STATES = {"installing_dependencies", "downloading_assets", "verifying"}
_thread: threading.Thread | None = None
_lock = threading.Lock()


def current_python() -> tuple[str, int]:
    return sys.version.split()[0], struct.calcsize("P") * 8


def is_supported(version: tuple[int, int], bits: int) -> bool:
    return version == (3, 13) and bits == 64


def _base_status() -> dict[str, Any]:
    version, bits = current_python()
    supported = is_supported(tuple(map(int, version.split(".")[:2])), bits)
    if supported:
        message = "本机 Python 3.13 x64 可一键配置；开始前请保持网络连接。"
        state = "idle"
    else:
        message = f"Python {version} 可继续使用文字模式；完整语音请查看手动配置教程。"
        state = "unsupported"
    return {
        "state": state,
        "supported": supported,
        "python_version": version,
        "python_bits": bits,
        "progress": 0,
        "message": message,
        "restart_required": False,
        "error": "",
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _write_status(**changes: Any) -> dict[str, Any]:
    status = _base_status()
    if STATUS_FILE.is_file():
        try:
            status.update(json.loads(STATUS_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            pass
    status.update(changes)
    status["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATUS_FILE)
    return status


def get_status() -> dict[str, Any]:
    status = _base_status()
    if STATUS_FILE.is_file():
        try:
            status.update(json.loads(STATUS_FILE.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return status
    if not status["supported"]:
        status.update(_base_status())
    return status


def setup_commands() -> list[list[str]]:
    return [
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "-r",
            str(ROOT / "backend" / "requirements.txt"),
        ],
        [sys.executable, str(ROOT / "backend" / "tools" / "download_runtime_assets.py")],
        [sys.executable, "-c", "import faster_whisper, sherpa_onnx, numpy"],
    ]


def run_setup() -> None:
    version, bits = current_python()
    if not is_supported(tuple(map(int, version.split(".")[:2])), bits):
        _write_status(**_base_status())
        return
    stages = [
        ("installing_dependencies", 10, "正在安装本地语音依赖…"),
        ("downloading_assets", 45, "正在下载 FFmpeg、Whisper 和说话人分离模型…"),
        ("verifying", 90, "正在检查语音依赖…"),
    ]
    try:
        for command, (state, progress, message) in zip(setup_commands(), stages, strict=True):
            _write_status(state=state, progress=progress, message=message, error="", restart_required=False)
            subprocess.run(command, cwd=ROOT, check=True)
        _write_status(
            state="restart_required",
            progress=100,
            message="语音组件已配置。请关闭当前窗口并重启 ADS 后再使用语音。",
            restart_required=True,
            error="",
        )
    except Exception as exc:  # noqa: BLE001
        _write_status(
            state="failed",
            message="语音配置未完成，文字模式不受影响。请检查网络后重试或查看手动配置教程。",
            restart_required=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def start_setup() -> dict[str, Any]:
    global _thread
    with _lock:
        status = get_status()
        if not status["supported"]:
            raise ValueError(status["message"])
        if _thread and _thread.is_alive():
            return status
        started = _write_status(
            state="installing_dependencies",
            progress=5,
            message="语音配置已开始，请保持 ADS 运行和网络连接。",
            restart_required=False,
            error="",
        )
        _thread = threading.Thread(target=run_setup, name="speech-setup", daemon=True)
        _thread.start()
        return started
