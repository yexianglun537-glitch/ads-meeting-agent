from pathlib import Path

from app import speech_setup


def test_only_python_313_x64_is_supported():
    assert speech_setup.is_supported((3, 13), 64)
    assert not speech_setup.is_supported((3, 11), 64)
    assert not speech_setup.is_supported((3, 12), 64)
    assert not speech_setup.is_supported((3, 14), 64)
    assert not speech_setup.is_supported((3, 13), 32)


def test_setup_commands_are_fixed_to_current_interpreter_and_project(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(speech_setup, "ROOT", tmp_path)
    monkeypatch.setattr(speech_setup.sys, "executable", str(tmp_path / "python.exe"))

    commands = speech_setup.setup_commands()

    assert commands == [
        [
            str(tmp_path / "python.exe"),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "-r",
            str(tmp_path / "backend" / "requirements.txt"),
        ],
        [
            str(tmp_path / "python.exe"),
            str(tmp_path / "backend" / "tools" / "download_runtime_assets.py"),
        ],
        [
            str(tmp_path / "python.exe"),
            "-c",
            "import faster_whisper, sherpa_onnx, numpy",
        ],
    ]


def test_idle_status_explains_manual_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(speech_setup, "STATUS_FILE", tmp_path / "speech-setup.json")
    monkeypatch.setattr(speech_setup, "current_python", lambda: ("3.12.9", 64))

    status = speech_setup.get_status()

    assert status["state"] == "unsupported"
    assert status["supported"] is False
    assert status["python_version"] == "3.12.9"
    assert "文字模式" in status["message"]
    assert "手动配置教程" in status["message"]


def test_finished_setup_requires_manual_restart(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(speech_setup, "STATUS_FILE", tmp_path / "speech-setup.json")
    monkeypatch.setattr(speech_setup, "current_python", lambda: ("3.13.12", 64))
    monkeypatch.setattr(speech_setup, "setup_commands", lambda: [["step-1"], ["step-2"], ["step-3"]])
    monkeypatch.setattr(speech_setup.subprocess, "run", lambda *args, **kwargs: None)

    speech_setup.run_setup()
    status = speech_setup.get_status()

    assert status["state"] == "restart_required"
    assert status["progress"] == 100
    assert status["restart_required"] is True
    assert "重启 ADS" in status["message"]


def test_fast_background_job_cannot_be_overwritten_by_start_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(speech_setup, "STATUS_FILE", tmp_path / "speech-setup.json")
    monkeypatch.setattr(speech_setup, "current_python", lambda: ("3.13.12", 64))
    monkeypatch.setattr(speech_setup, "_thread", None)

    def finish_immediately():
        speech_setup._write_status(state="restart_required", progress=100, restart_required=True)

    class ImmediateThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

        def is_alive(self):
            return False

    monkeypatch.setattr(speech_setup, "run_setup", finish_immediately)
    monkeypatch.setattr(speech_setup.threading, "Thread", ImmediateThread)

    started = speech_setup.start_setup()

    assert started["state"] == "installing_dependencies"
    assert speech_setup.get_status()["state"] == "restart_required"
