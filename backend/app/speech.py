"""Local speech-to-text adapter used by the meeting input layer.

The module deliberately imports faster-whisper lazily so the rest of the demo
can still start and explain how to recover when the offline model is missing.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


def _backend_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


AUDIO_ROOT = _backend_path(os.getenv("ADS_AUDIO_DIR", os.getenv("SPEECH_AUDIO_DIR", "data/audio")))
MODEL_PATH = _backend_path(
    os.getenv("WHISPER_MODEL_PATH", os.getenv("SPEECH_MODEL_DIR", "data/models/faster-whisper-small"))
)
MODEL_NAME = os.getenv("WHISPER_MODEL", "faster-whisper-small")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(500 * 1024 * 1024)))
MAX_AUDIO_SECONDS = 4 * 60 * 60
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")
SIMPLIFIED_CHINESE_PROMPT = "以下是简体中文普通话会议记录，请使用简体中文。"
LCMAP_SIMPLIFIED_CHINESE = 0x02000000


@dataclass
class SpeechRuntime:
    ready: bool
    ffmpeg_available: bool
    model_available: bool
    message: str


def to_simplified_chinese(text: str) -> str:
    if not text or os.name != "nt":
        return text
    mapper = ctypes.windll.kernel32.LCMapStringEx
    size = mapper("zh-CN", LCMAP_SIMPLIFIED_CHINESE, text, -1, None, 0, None, None, 0)
    if size <= 0:
        return text
    output = ctypes.create_unicode_buffer(size)
    return output.value if mapper("zh-CN", LCMAP_SIMPLIFIED_CHINESE, text, -1, output, size, None, None, 0) else text


def _ffmpeg() -> str | None:
    if FFMPEG_PATH:
        configured = _backend_path(FFMPEG_PATH)
        if configured.exists():
            return str(configured)
    bundled = BACKEND_DIR / "vendor" / "ffmpeg" / "ffmpeg.exe"
    runtime = PROJECT_DIR / "runtime" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if bundled.exists():
        return str(bundled)
    if runtime.exists():
        return str(runtime)
    return shutil.which("ffmpeg")


def _ffprobe() -> str | None:
    if FFMPEG_PATH:
        configured = _backend_path(FFMPEG_PATH)
        sibling = configured.with_name("ffprobe.exe")
        if sibling.exists():
            return str(sibling)
    bundled = BACKEND_DIR / "vendor" / "ffmpeg" / "ffprobe.exe"
    runtime = PROJECT_DIR / "runtime" / "ffmpeg" / "bin" / "ffprobe.exe"
    if bundled.exists():
        return str(bundled)
    if runtime.exists():
        return str(runtime)
    return shutil.which("ffprobe")


def runtime() -> SpeechRuntime:
    ffmpeg_available = bool(_ffmpeg())
    model_available = MODEL_PATH.is_dir() and (MODEL_PATH / "model.bin").is_file()
    try:
        import faster_whisper  # noqa: F401

        package_available = True
    except ImportError:
        package_available = False
    ready = ffmpeg_available and model_available and package_available
    missing = []
    if not ffmpeg_available:
        missing.append("FFmpeg")
    if not package_available:
        missing.append("faster-whisper")
    if not model_available:
        missing.append("本地模型")
    return SpeechRuntime(
        ready=ready,
        ffmpeg_available=ffmpeg_available,
        model_available=model_available and package_available,
        message="离线语音转写可用" if ready else f"缺少：{'、'.join(missing)}；仍可使用文字输入",
    )


def save_upload(job_id: str, filename: str, content: bytes) -> Path:
    if not content:
        raise ValueError("empty_audio")
    if len(content) > MAX_AUDIO_BYTES:
        raise ValueError("audio_too_large")
    suffix = Path(filename).suffix.lower() or ".webm"
    if suffix not in {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".webm", ".mp4", ".flac"}:
        raise ValueError("unsupported_format")
    raw_dir = AUDIO_ROOT / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"{job_id}{suffix}"
    target.write_bytes(content)
    return target


def probe_duration(source: Path) -> float | None:
    ffprobe = _ffprobe()
    if not ffprobe or not source.exists():
        return None
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return round(duration, 2) if duration > 0 else None


def source_for_job(job_id: str) -> Path | None:
    raw_dir = AUDIO_ROOT / "raw"
    matches = sorted(raw_dir.glob(f"{job_id}.*"))
    return matches[0] if matches else None


def delete_audio_assets(job_id: str) -> None:
    for directory in (AUDIO_ROOT / "raw", AUDIO_ROOT / "normalized"):
        for path in directory.glob(f"{job_id}.*"):
            if path.is_file():
                path.unlink()


def transcribe(
    job_id: str,
    source: Path,
    language: str = "zh",
    progress_callback: Callable[[int], None] | None = None,
    word_timestamps: bool = False,
    progress_ceiling: int = 95,
) -> list[dict]:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_missing")
    normalized_dir = AUDIO_ROOT / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    normalized = normalized_dir / f"{job_id}.wav"
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(source), "-ac", "1", "-ar", "16000", str(normalized)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError("ffmpeg_failed")
    duration = probe_duration(normalized) or probe_duration(source)
    model = _whisper_model()
    segments, _ = model.transcribe(
        str(normalized),
        language=language or "zh",
        vad_filter=True,
        beam_size=5,
        initial_prompt=SIMPLIFIED_CHINESE_PROMPT,
        word_timestamps=word_timestamps,
    )
    result_segments: list[dict] = []
    for segment in segments:
        text = to_simplified_chinese(segment.text.strip())
        if not text:
            continue
        start = float(segment.start)
        end = float(segment.end)
        item = {"start": start, "end": end, "text": text}
        if word_timestamps:
            item["words"] = [
                {
                    "start": float(word.start),
                    "end": float(word.end),
                    "text": to_simplified_chinese(word.word),
                }
                for word in (getattr(segment, "words", None) or [])
                if word.start is not None and word.end is not None and word.word
            ]
        result_segments.append(item)
        if progress_callback and duration:
            progress_callback(
                min(progress_ceiling, max(56, 55 + round((end / duration) * (progress_ceiling - 55))))
            )
    return result_segments


def normalized_audio_path(job_id: str) -> Path:
    return AUDIO_ROOT / "normalized" / f"{job_id}.wav"


@lru_cache(maxsize=1)
def _whisper_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("model_missing") from exc
    if not (MODEL_PATH / "model.bin").is_file():
        raise RuntimeError("model_missing")
    return WhisperModel(str(MODEL_PATH), device=DEVICE, compute_type=COMPUTE_TYPE, local_files_only=True)
