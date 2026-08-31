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


def check_runtime(resources: Path, port: int, *, lightweight: bool = False) -> int:
    required = [resources / "frontend" / "dist" / "index.html"]
    if not lightweight:
        required.extend(
            [
                resources / "runtime" / "ffmpeg" / "bin" / "ffmpeg.exe",
                resources / "runtime" / "ffmpeg" / "bin" / "ffprobe.exe",
                resources / "backend" / "data" / "models" / "faster-whisper-small" / "model.bin",
                resources / "backend" / "data" / "models" / "speaker-diarization" / "segmentation" / "model.onnx",
                resources / "backend" / "data" / "models" / "speaker-diarization" / "wespeaker_zh_cnceleb_resnet34.onnx",
            ]
        )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("发行包缺少必要文件：\n" + "\n".join(missing))
    required_space = 100 * 1024 * 1024 if lightweight else 1024 * 1024 * 1024
    if shutil.disk_usage(application_root()).free < required_space:
        amount = "100 MB" if lightweight else "1 GB"
        raise RuntimeError(f"可用磁盘空间不足 {amount}，请释放空间后重试。")
    ports = range(port, port + 11) if lightweight else (port,)
    for candidate_port in ports:
        with socket.socket() as candidate:
            try:
                candidate.bind(("127.0.0.1", candidate_port))
                return candidate_port
            except OSError:
                pass
    if lightweight:
        raise RuntimeError(f"端口 {port}-{port + 10} 均被占用，请关闭占用程序后重试。")
    raise RuntimeError(f"端口 {port} 已被占用，请关闭占用程序或使用 --port 指定其他端口。")


def wait_until_ready(url: str, server_thread: threading.Thread | None = None) -> bool:
    health = f"{url}/api/health"
    for _ in range(80):
        try:
            with urllib.request.urlopen(health, timeout=1) as response:
                if response.status == 200:
                    return True
        except OSError:
            if server_thread is not None and not server_thread.is_alive():
                return False
        time.sleep(0.25)
    return False


def open_when_ready(url: str) -> None:
    if wait_until_ready(url):
        webbrowser.open(url)


def main() -> int:
    parser = argparse.ArgumentParser(description="ADS 会议智能体 Windows 启动器")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--lightweight", action="store_true")
    args = parser.parse_args()
    try:
        resources, logs = configure_runtime()
        logging.basicConfig(filename=logs / "ads-agent.log", level=logging.INFO, encoding="utf-8", format="%(asctime)s %(levelname)s %(message)s")
        port = check_runtime(resources, args.port, lightweight=args.lightweight)
        if str(resources / "backend") not in sys.path:
            sys.path.insert(0, str(resources / "backend"))
        from app.main import app
        import uvicorn

        url = f"http://127.0.0.1:{port}"
        if args.lightweight:
            server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
            startup_errors: list[BaseException] = []

            def run_server() -> None:
                try:
                    server.run()
                except BaseException as exc:
                    startup_errors.append(exc)

            server_thread = threading.Thread(target=run_server, name="ads-uvicorn")
            server_thread.start()
            if not wait_until_ready(url, server_thread):
                server.should_exit = True
                server_thread.join(timeout=5)
                if startup_errors:
                    raise RuntimeError(f"服务启动失败：{startup_errors[0]}") from startup_errors[0]
                raise RuntimeError("服务健康检查超时，请查看日志后重试。")
            print(f"ADS 会议智能体已启动：{url}")
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server_thread.join()
            except KeyboardInterrupt:
                server.should_exit = True
                server_thread.join()
            return 0
        if not args.no_browser:
            threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)
        return 0
    except Exception as exc:
        message = f"ADS 会议智能体启动失败：{exc}"
        logging.exception(message)
        print(message, file=sys.stderr)
        print(f"日志位置：{application_root() / 'logs' / 'ads-agent.log'}", file=sys.stderr)
        print("完整 Windows 发行版：https://github.com/yexianglun537-glitch/ads-meeting-agent/releases", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
