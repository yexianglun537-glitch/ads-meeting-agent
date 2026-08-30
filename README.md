# ADS 会议智能体

ADS 会议智能体是一套本地运行的会议协作工具，用于管理会前准备、本人或智能体参会、超权决策确认、会议纪要、行动项和 ADS 工作区回写。

当前实现采用 React、FastAPI 和 SQLite，支持文字输入、浏览器录音、音频文件转写、本地 faster-whisper、可切换在线模型和本地规则模式。

## 当前能力

- 创建会议并关联业务工作区、人员、目标、任务和授权规则。
- 生成会前简报和建议议程。
- 由本人参加，或确认委托 ADS 智能体代理参会。
- 处理文字发言、麦克风录音和音频文件。
- 在授权范围内继续处理会议，将超权事项单独送入决策中心。
- 形成结构化纪要、决策和行动项。
- 确认行动项后写回 ADS 工作区并保留审计来源。
- 使用 SQLite 保存会议、工作区、任务、模型配置和转写任务。

产品范围、UI、实施顺序和未完成项统一以 [当前产品需求与验收标准](docs/requirements/ADS会议智能体当前产品需求与验收标准.md) 为唯一基线，不能仅根据构建或测试通过判断整个产品已经完成。

## 一键启动

在项目根目录双击：

```text
启动项目.bat
```

或者在 PowerShell 中运行：

```powershell
.\start-dev.ps1
```

启动脚本会检查环境、安装缺失依赖并启动：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

面向普通 Windows 用户的发行包使用 PyInstaller one-folder 构建。解压 ZIP 后直接运行 `ADS会议智能体.exe`，无需预装 Python、Node、Git、FFmpeg 或 Whisper；数据库、音频、备份和日志写入解压目录下的 `data/` 与 `logs/`。

开发机生成发行包：

```powershell
.\packaging\build-release.ps1 -Version 0.1.0
```

构建机需在项目虚拟环境中预装 PyInstaller；脚本会先执行前端测试、类型检查、构建和后端测试，任一步失败都不会生成 ZIP。

## 本地语音组件

运行本地转写需要以下文件：

```text
runtime/ffmpeg/bin/ffmpeg.exe
runtime/ffmpeg/bin/ffprobe.exe
backend/data/models/faster-whisper-small/model.bin
```

安装完整的本地语音运行资源：

```powershell
Set-Location backend
.\.venv\Scripts\python.exe tools\download_runtime_assets.py
```

该命令下载并校验 FFmpeg、Whisper 模型所需的配置/权重/分词器/词表，以及匿名说话人分离模型。只使用文字会议流程时可以跳过。

语音运行状态：

```text
http://127.0.0.1:8000/api/speech/health
```

只有返回 `status: ready`、`ffmpeg_available: true` 和 `model_available: true` 时，才表示本地转写组件已经就绪。

## 模型配置

本地配置位于 `backend/.env`。默认 `USE_MOCK_AI=true`，会议分析使用本地规则模式；切换为在线模型时改为：

```env
USE_MOCK_AI=false
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

也可以在产品设置页配置 DeepSeek 或 OpenAI-compatible 模型。API Key 只保存在本地后端，不应写入前端、文档或版本库。

## 手动启动

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

## 验证

后端测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests
```

前端测试与生产构建：

```powershell
cd frontend
npm test
npm run build
```

## 数据与运行文件

- SQLite 数据：`backend/data/ads_agent.db`
- 原始与标准化音频：`backend/data/audio/`
- 本地模型：`backend/data/models/faster-whisper-small/`
- FFmpeg：`runtime/ffmpeg/`
- 运行日志：`logs/`

不要通过手动删除数据库或音频文件清理产品数据，应优先使用对应的产品操作或后端接口。

## 文档

源码包内的核心文档包括：

- [当前产品需求与验收标准](docs/requirements/ADS会议智能体当前产品需求与验收标准.md)
- [本地语音转文字工具需求](docs/requirements/ADS会议智能体本地语音转文字工具需求文档.md)
- [ADS会议智能体使用教程](docs/guides/ADS会议智能体使用教程.md)
- [ADS核心Prompt与工作流说明](docs/ADS核心Prompt与工作流说明.md)

第三方组件来源和许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
