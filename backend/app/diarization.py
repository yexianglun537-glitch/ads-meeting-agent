"""Local anonymous speaker diarization and timestamp alignment."""

from __future__ import annotations

import os
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _backend_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


MODEL_DIR = _backend_path(os.getenv("DIARIZATION_MODEL_DIR", "data/models/speaker-diarization"))
SEGMENTATION_MODEL_PATH = MODEL_DIR / "segmentation" / "model.onnx"
EMBEDDING_MODEL_PATH = MODEL_DIR / "wespeaker_zh_cnceleb_resnet34.onnx"
MODEL_NAME = "sherpa-onnx-pyannote3-wespeaker-zh"
CLUSTER_THRESHOLD = float(os.getenv("DIARIZATION_CLUSTER_THRESHOLD", "0.6"))


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: int


@dataclass(frozen=True)
class DiarizationRuntime:
    ready: bool
    package_available: bool
    model_available: bool
    message: str


def runtime() -> DiarizationRuntime:
    try:
        import sherpa_onnx  # noqa: F401

        package_available = True
    except ImportError:
        package_available = False
    model_available = SEGMENTATION_MODEL_PATH.is_file() and EMBEDDING_MODEL_PATH.is_file()
    ready = package_available and model_available
    missing: list[str] = []
    if not package_available:
        missing.append("sherpa-onnx")
    if not model_available:
        missing.append("说话人分离模型")
    return DiarizationRuntime(
        ready=ready,
        package_available=package_available,
        model_available=model_available,
        message="本地匿名说话人分离可用" if ready else f"缺少：{'、'.join(missing)}",
    )


def _overlap(start: float, end: float, turn: SpeakerTurn) -> float:
    return max(0.0, min(end, turn.end) - max(start, turn.start))


def _speaker_for_interval(
    start: float, end: float, turns: list[SpeakerTurn]
) -> tuple[int | None, bool]:
    scored = [(_overlap(start, end, turn), turn) for turn in turns]
    scored = [(overlap, turn) for overlap, turn in scored if overlap > 0]
    if not scored:
        if not turns:
            return None, False

        def distance(turn: SpeakerTurn) -> float:
            if end <= turn.start:
                return turn.start - end
            if start >= turn.end:
                return start - turn.end
            return 0.0

        nearest = min(turns, key=lambda turn: (distance(turn), turn.start, turn.speaker))
        return nearest.speaker, False
    scored.sort(key=lambda item: (-item[0], item[1].start, item[1].speaker))
    best = scored[0][1]
    duration = max(0.01, end - start)
    meaningful = max(0.03, duration * 0.05)
    overlapping_speakers = {turn.speaker for overlap, turn in scored if overlap >= meaningful}
    return best.speaker, len(overlapping_speakers) > 1


def _segment_units(segment: dict) -> list[dict]:
    words = [
        word
        for word in segment.get("words", [])
        if word.get("text") and word.get("start") is not None and word.get("end") is not None
    ]
    if words:
        return [
            {
                "start": float(word["start"]),
                "end": float(word["end"]),
                "text": str(word["text"]),
            }
            for word in words
        ]
    return [
        {
            "start": float(segment["start"]),
            "end": float(segment["end"]),
            "text": str(segment["text"]),
        }
    ]


def assign_speakers(segments: list[dict], turns: list[SpeakerTurn]) -> list[dict]:
    """Assign transcript words to speaker turns and regroup on speaker changes."""

    grouped: list[dict] = []
    for segment in segments:
        current: dict | None = None
        for unit in _segment_units(segment):
            speaker, ambiguous = _speaker_for_interval(unit["start"], unit["end"], turns)
            if current is not None and current["speaker"] == speaker:
                current["end"] = unit["end"]
                current["text"] = f"{current['text']}{unit['text']}"
                current["speaker_ambiguous"] = current["speaker_ambiguous"] or ambiguous
                continue
            current = {
                "start": unit["start"],
                "end": unit["end"],
                "text": unit["text"],
                "speaker": speaker,
                "speaker_ambiguous": ambiguous,
            }
            grouped.append(current)

    label_by_speaker: dict[int | None, str] = {}
    for item in grouped:
        speaker = item.pop("speaker")
        if speaker not in label_by_speaker:
            label_by_speaker[speaker] = f"发言人 {len(label_by_speaker) + 1}"
        item["speaker_label"] = label_by_speaker[speaker]
        item["text"] = item["text"].strip()
    return grouped


def _read_pcm_wav(path: Path):
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("diarization_runtime_missing") from exc
    try:
        with wave.open(str(path), "rb") as audio:
            if audio.getnchannels() != 1 or audio.getframerate() != 16_000 or audio.getsampwidth() != 2:
                raise RuntimeError("diarization_audio_invalid")
            frames = audio.readframes(audio.getnframes())
    except (OSError, wave.Error) as exc:
        raise RuntimeError("diarization_audio_invalid") from exc
    if not frames:
        raise RuntimeError("diarization_no_speakers")
    return np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0


@lru_cache(maxsize=10)
def _diarizer(speaker_count: int | None):
    if speaker_count is not None and not 2 <= speaker_count <= 10:
        raise ValueError("invalid_speaker_count")
    if not SEGMENTATION_MODEL_PATH.is_file() or not EMBEDDING_MODEL_PATH.is_file():
        raise RuntimeError("diarization_model_missing")
    try:
        import sherpa_onnx
    except ImportError as exc:
        raise RuntimeError("diarization_runtime_missing") from exc
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(SEGMENTATION_MODEL_PATH),
                window_shift_ratio=0.1,
            )
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(EMBEDDING_MODEL_PATH)),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=speaker_count if speaker_count is not None else -1,
            threshold=CLUSTER_THRESHOLD,
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise RuntimeError("diarization_model_invalid")
    return sherpa_onnx.OfflineSpeakerDiarization(config)


def diarize(
    audio_path: Path,
    speaker_count: int | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> list[SpeakerTurn]:
    samples = _read_pcm_wav(audio_path)
    engine = _diarizer(speaker_count)

    def report(processed: int, total: int) -> int:
        if progress_callback and total > 0:
            progress_callback(min(100, max(0, round(processed / total * 100))))
        return 0

    result = engine.process(samples, callback=report).sort_by_start_time()
    turns = [
        SpeakerTurn(start=float(item.start), end=float(item.end), speaker=int(item.speaker))
        for item in result
        if float(item.end) > float(item.start)
    ]
    if not turns:
        raise RuntimeError("diarization_no_speakers")
    return turns
