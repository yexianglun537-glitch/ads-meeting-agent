from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import tarfile
import time
import zipfile
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "backend" / "data" / "models" / "faster-whisper-small"
MODEL_BASE_URL = "https://huggingface.co/Systran/faster-whisper-small/resolve/main"
WHISPER_FILES = {
    "config.json": f"{MODEL_BASE_URL}/config.json",
    "model.bin": f"{MODEL_BASE_URL}/model.bin",
    "tokenizer.json": f"{MODEL_BASE_URL}/tokenizer.json",
    "vocabulary.txt": f"{MODEL_BASE_URL}/vocabulary.txt",
}
FFMPEG_ZIP = ROOT / "runtime" / "ffmpeg-release-essentials.zip"
FFMPEG_DIR = ROOT / "runtime" / "ffmpeg"
DIARIZATION_DIR = ROOT / "backend" / "data" / "models" / "speaker-diarization"
SEGMENTATION_ARCHIVE = DIARIZATION_DIR / "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
SEGMENTATION_MODEL = DIARIZATION_DIR / "segmentation" / "model.onnx"
EMBEDDING_MODEL = DIARIZATION_DIR / "wespeaker_zh_cnceleb_resnet34.onnx"
SEGMENTATION_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMBEDDING_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_zh_cnceleb_resnet34.onnx"
SEGMENTATION_SHA256 = "220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079"
EMBEDDING_SHA256 = "f86cd6c509f331f0e20b07bd48d1b2eb7de54202643401c4e84695ac861a0e5a"


def download(url: str, target: Path, retries: int = 20) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        print(f"already present {target} ({target.stat().st_size} bytes)")
        return
    part = target.with_name(f"{target.name}.part")
    total_size: int | None = None

    for attempt in range(1, retries + 1):
        done = part.stat().st_size if part.exists() else target.stat().st_size if target.exists() else 0
        headers = {"Range": f"bytes={done}-"} if done else {}
        mode = "ab" if done else "wb"
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as response:
                response.raise_for_status()
                if done and response.status_code != 206:
                    done = 0
                    mode = "wb"
                content_range = response.headers.get("Content-Range", "")
                match = re.search(r"/(\d+)$", content_range)
                if match:
                    total_size = int(match.group(1))
                elif response.headers.get("Content-Length"):
                    total_size = done + int(response.headers["Content-Length"])

                with part.open(mode) as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)

            current = part.stat().st_size
            if total_size is None or current >= total_size:
                part.replace(target)
                print(f"downloaded {target} ({target.stat().st_size} bytes)")
                return
            print(f"partial {target.name}: {current}/{total_size} bytes")
        except Exception as exc:  # noqa: BLE001
            current = part.stat().st_size if part.exists() else 0
            print(f"retry {attempt}/{retries} after {type(exc).__name__}: {current} bytes")
            time.sleep(min(10, attempt))

    raise RuntimeError(f"failed to download {target}")


def install_ffmpeg(zip_path: Path) -> None:
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        members = [
            item
            for item in archive.namelist()
            if item.endswith("/bin/ffmpeg.exe") or item.endswith("/bin/ffprobe.exe")
        ]
        if len(members) < 2:
            raise RuntimeError("ffmpeg zip does not contain ffmpeg.exe and ffprobe.exe")
        for member in members:
            name = Path(member).name
            target = FFMPEG_DIR / "bin" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                output.write(source.read())
            print(f"installed {target}")


def verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected.lower():
        raise RuntimeError(f"checksum mismatch for {path}")
    print(f"verified {path} sha256={expected.upper()}")


def install_segmentation_model(archive_path: Path) -> None:
    with tarfile.open(archive_path, "r:bz2") as archive:
        members = [item for item in archive.getmembers() if item.isfile() and Path(item.name).name == "model.onnx"]
        if len(members) != 1:
            raise RuntimeError("speaker segmentation archive does not contain exactly one model.onnx")
        source = archive.extractfile(members[0])
        if source is None:
            raise RuntimeError("speaker segmentation model cannot be read")
        SEGMENTATION_MODEL.parent.mkdir(parents=True, exist_ok=True)
        with source, SEGMENTATION_MODEL.open("wb") as output:
            shutil.copyfileobj(source, output)
    print(f"installed {SEGMENTATION_MODEL} ({SEGMENTATION_MODEL.stat().st_size} bytes)")
    archive_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="store_true")
    parser.add_argument("--ffmpeg", action="store_true")
    parser.add_argument("--diarization", action="store_true")
    args = parser.parse_args()
    all_assets = not args.model and not args.ffmpeg and not args.diarization

    if args.model or all_assets:
        for name, url in WHISPER_FILES.items():
            download(url, MODEL_DIR / name)

    if args.ffmpeg or all_assets:
        download("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", FFMPEG_ZIP)
        install_ffmpeg(FFMPEG_ZIP)

    if args.diarization or all_assets:
        if SEGMENTATION_MODEL.is_file():
            print(f"already present {SEGMENTATION_MODEL} ({SEGMENTATION_MODEL.stat().st_size} bytes)")
        else:
            download(SEGMENTATION_URL, SEGMENTATION_ARCHIVE)
            install_segmentation_model(SEGMENTATION_ARCHIVE)
        download(EMBEDDING_URL, EMBEDDING_MODEL)
        verify_sha256(SEGMENTATION_MODEL, SEGMENTATION_SHA256)
        verify_sha256(EMBEDDING_MODEL, EMBEDDING_SHA256)


if __name__ == "__main__":
    main()
