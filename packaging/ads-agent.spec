from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project = Path(SPECPATH).parent
backend = project / "backend"
hiddenimports = []
binaries = []
datas = [
    (str(project / "frontend" / "dist"), "frontend/dist"),
    (str(project / "runtime" / "ffmpeg"), "runtime/ffmpeg"),
    (str(project / "backend" / "data" / "models" / "faster-whisper-small"), "backend/data/models/faster-whisper-small"),
    (str(project / "backend" / "data" / "models" / "speaker-diarization"), "backend/data/models/speaker-diarization"),
    (str(project / "README.md"), "."),
    (str(project / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project / "docs" / "guides" / "ADS会议智能体使用教程.md"), "docs"),
]
for package in ("faster_whisper", "ctranslate2", "av", "sherpa_onnx"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(project / "packaging" / "launcher.py")],
    pathex=[str(backend)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ADS会议智能体", console=True, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ADS会议智能体")
