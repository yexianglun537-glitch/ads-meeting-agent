# 第三方语音组件说明

## FFmpeg

- 版本：`9.0.1-essentials_build-www.gyan.dev`
- 来源：https://www.gyan.dev/ffmpeg/builds/
- 上游：https://ffmpeg.org/
- 对应上游源码：https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz
- 上游许可证说明：https://ffmpeg.org/legal.html
- GNU GPL v3 文本：https://www.gnu.org/licenses/gpl-3.0.html
- 项目路径：`runtime/ffmpeg/bin/`
- 当前二进制的 `ffmpeg -version` 显示启用了 `--enable-gpl`、`--enable-version3` 和 GPL 编解码库，因此本项目按 GPL v3 分发边界处理，不把 FFmpeg 视为项目自有代码。
- 发行包必须同时保留本文件中的构建来源、对应源码获取地址和许可证地址；接收者可以从上述 FFmpeg 9.0.1 源码地址取得对应上游源码。
- `ffmpeg.exe` SHA-256：`72A489ECCD008C2EC2C0A5856C5C75BC3D8BBFA90166C4566865C246445E6AA3`
- `ffprobe.exe` SHA-256：`19202B23C0043F15AD1B7BCE2344F406FD52BD6EFD8F995CE02E7392A1CEC52F`

## faster-whisper small

- 模型：`Systran/faster-whisper-small`
- 来源：https://huggingface.co/Systran/faster-whisper-small
- 基础模型：https://huggingface.co/openai/whisper-small
- 项目路径：`backend/data/models/faster-whisper-small/`
- 模型仓库声明为 MIT License；最终分发时应保留模型目录中的 `README.md` 和相关许可信息。
- `model.bin` SHA-256：`3E305921506D8872816023E4C273E75D2419FB89B24DA97B4FE7BCE14170D671`

## Python 运行库

- 当前直接依赖以 `backend/requirements.txt` 为准：FastAPI、Uvicorn、Pydantic、python-dotenv、httpx、python-multipart、faster-whisper、sherpa-onnx、NumPy 和 requests。
- `ctranslate2`、`av` 等传递依赖由上述直接依赖安装，并由 PyInstaller 收集进入发行目录。
- 本文件只确认项目直接依赖和 FFmpeg/faster-whisper 模型来源；正式外部分发前仍应从实际发行目录生成并人工复核完整 Python 传递依赖许可证清单。

## sherpa-onnx 与匿名说话人分离模型

- 运行库：`sherpa-onnx 1.13.6`，Apache License 2.0。
- 运行库来源：https://github.com/k2-fsa/sherpa-onnx
- 分段模型：`sherpa-onnx-pyannote-segmentation-3-0/model.onnx`。
- 分段模型来源：https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-segmentation-models
- 原始模型卡：https://huggingface.co/pyannote/segmentation-3.0 ，声明为 MIT License。
- 中文声音特征模型：`wespeaker_zh_cnceleb_resnet34.onnx`。
- 模型来源：https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models
- 上游 WeSpeaker：https://github.com/wenet-e2e/wespeaker ，Apache License 2.0。
- 项目路径：`backend/data/models/speaker-diarization/`。
- `segmentation/model.onnx` SHA-256：`220AD67CA923BEF2FA91F2390C786097BF305BCEB5E261D4AF67B38E938E1079`
- `wespeaker_zh_cnceleb_resnet34.onnx` SHA-256：`F86CD6C509F331F0E20B07BD48D1B2EB7DE54202643401C4E84695AC861A0E5A`
- sherpa-onnx 模型发布页明确提示每个声音特征模型具有各自许可；发行时同时保留本说明、sherpa-onnx Apache-2.0、pyannote segmentation MIT 和 WeSpeaker Apache-2.0 来源信息。

## 前端运行库

- 当前直接依赖以 `frontend/package.json` 为准：React、React DOM、Lucide React、Vite、TypeScript 和 React Vite 插件。
- 构建产物只包含实际打包使用的代码；正式外部分发前仍需按锁定版本复核前端直接及传递依赖许可证。

## Windows 发行包

- one-folder 发行目录保留本文件、项目 README、FFmpeg 可执行文件、模型仓库 README 和使用教程。
- 对外发布前仍需由发布负责人复核 FFmpeg GPL 分发材料，以及前端构建和 PyInstaller 收集的全部传递依赖许可证；构建成功不替代许可证合规审核。
