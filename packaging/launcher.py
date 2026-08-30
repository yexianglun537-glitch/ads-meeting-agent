from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def application_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", application_root()))


def configure_runtime() -> tuple[Path, Path]:
    root = application_root()
    resources = resource_root()
    data = root / "data"
    logs = root / "logs"
    for directory in (data, data / "audio", data / "backups", logs):
        directory.mkdir(parents=True, exist_ok=True)
    probe = data / ".write-test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    os.environ.setdefault("ADS_DB_PATH", str(data / "ads_agent.db"))
    os.environ.setdefault("ADS_AUDIO_DIR", str(data / "audio"))
    os.environ.setdefault("ADS_BACKUP_DIR", str(data / "backups"))
    os.environ.setdefault("ADS_FRONTEND_DIST", str(resources / "frontend" / "dist"))
    os.environ.setdefault("FFMPEG_PATH", str(resources / "runtime" / "ffmpeg" / "bin" / "ffmpeg.exe"))
    os.environ.setdefault("SPEECH_MODEL_DIR", str(resources / "backend" / "data" / "models" / "faster-whisper-small"))
    os.environ.setdefault("DIARIZATION_MODEL_DIR", str(resources / "backend" / "data" / "models" / "speaker-diarization"))
    os.environ.setdefault("USE_MOCK_AI", "true")
    return resources, logs


def check_runtime(resources: Path, port: int) -> None:
    required = [
        resources / "frontend" / "dist" / "index.html",
        resources / "runtime" / "ffmpeg" / "bin" / "ffmpeg.exe",
        resources / "runtime" / "ffmpeg" / "bin" / "ffprobe.exe",
        resources / "backend" / "data" / "models" / "faster-whisper-small" / "model.bin",
        resources / "backend" / "data" / "models" / "speaker-diarization" / "segmentation" / "model.onnx",
        resources / "backend" / "data" / "models" / "speaker-diarization" / "wespeaker_zh_cnceleb_resnet34.onnx",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("发行包缺少必要文件：\n" + "\n".join(missing))
    if shutil.disk_usage(application_root()).free < 1024 * 1024 * 1024:
        raise RuntimeError("可用磁盘空间不足 1 GB，请释放空间后重试。")
    with socket.socket() as candidate:
        try:
            candidate.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"端口 {port} 已被占用，请关闭占用程序或使用 --port 指定其他端口。") from exc


def open_when_ready(url: str) -> None:
    health = f"{url}/api/health"
    for _ in range(80):
        try:
            with urllib.request.urlopen(health, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.25)


def main() -> int:
    parser = argparse.ArgumentParser(description="ADS 会议智能体 Windows 启动器")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        resources, logs = configure_runtime()
        logging.basicConfig(filename=logs / "ads-agent.log", level=logging.INFO, encoding="utf-8", format="%(asctime)s %(levelname)s %(message)s")
        check_runtime(resources, args.port)
        if str(resources / "backend") not in sys.path:
            sys.path.insert(0, str(resources / "backend"))
        from app.main import app
        import uvicorn

        url = f"http://127.0.0.1:{args.port}"
        if not args.no_browser:
            threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_config=None)
        return 0
    except Exception as exc:
        message = f"ADS 会议智能体启动失败：{exc}"
        logging.exception(message)
        print(message, file=sys.stderr)
        print(f"日志位置：{application_root() / 'logs' / 'ads-agent.log'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
