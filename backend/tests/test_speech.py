from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import speech


def test_bundled_model_uses_a_stable_display_name() -> None:
    assert speech.MODEL_NAME == "faster-whisper-small"


def test_windows_speech_output_is_simplified_chinese(tmp_path: Path) -> None:
    model = Mock()
    model.transcribe.return_value = (
        [SimpleNamespace(start=0, end=3, text="楊隊十分鐘內把負責的部分講完，不要有廢話。")],
        None,
    )

    with (
        patch.object(speech, "AUDIO_ROOT", tmp_path),
        patch.object(speech, "_ffmpeg", return_value="ffmpeg.exe"),
        patch.object(speech.subprocess, "run", return_value=SimpleNamespace(returncode=0)),
        patch.object(speech, "probe_duration", return_value=3.0),
        patch.object(speech, "_whisper_model", return_value=model),
    ):
        segments = speech.transcribe("stt_simplified", tmp_path / "meeting.wav")

    assert segments[0]["text"] == "杨队十分钟内把负责的部分讲完，不要有废话。"
    assert model.transcribe.call_args.kwargs["initial_prompt"] == "以下是简体中文普通话会议记录，请使用简体中文。"


def test_transcription_can_return_word_timestamps_for_diarization(tmp_path: Path) -> None:
    model = Mock()
    model.transcribe.return_value = (
        [
            SimpleNamespace(
                start=0,
                end=2,
                text="你好，收到。",
                words=[
                    SimpleNamespace(start=0.0, end=0.8, word="你好，"),
                    SimpleNamespace(start=1.0, end=1.8, word="收到。"),
                ],
            )
        ],
        None,
    )

    with (
        patch.object(speech, "AUDIO_ROOT", tmp_path),
        patch.object(speech, "_ffmpeg", return_value="ffmpeg.exe"),
        patch.object(speech.subprocess, "run", return_value=SimpleNamespace(returncode=0)),
        patch.object(speech, "probe_duration", return_value=2.0),
        patch.object(speech, "_whisper_model", return_value=model),
    ):
        segments = speech.transcribe(
            "stt_words",
            tmp_path / "meeting.wav",
            word_timestamps=True,
        )

    assert model.transcribe.call_args.kwargs["word_timestamps"] is True
    assert segments[0]["words"] == [
        {"start": 0.0, "end": 0.8, "text": "你好，"},
        {"start": 1.0, "end": 1.8, "text": "收到。"},
    ]
