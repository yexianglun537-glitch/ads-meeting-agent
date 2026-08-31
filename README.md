# ADS 会议智能体

ADS 会议智能体是一套本地运行的会议协作工具，用于管理会前准备、本人或智能体参会、超权决策确认、会议纪要、行动项和 ADS 工作区回写。

当前实现采用 React、FastAPI 和 SQLite。产品支持文字输入、本地规则模式、在线模型、浏览器录音和本地音频转写；不同交付包包含的运行组件有所不同。

产品范围、UI、实施顺序和未完成项统一以[当前产品需求与验收标准](docs/requirements/ADS会议智能体当前产品需求与验收标准.md)为唯一产品基线。轻量源码包的环境与交付边界以[源码包兼容性交付要求](docs/requirements/2026-08-31-源码包兼容性交付要求.md)为准。

## 轻量源码包启动（平台提交版）

适用环境：Windows 10/11 x64，已安装 Python 3.11–3.14 的任一 64 位版本。

1. 完整解压 ZIP，不要直接在压缩包内运行。
2. 双击 `启动项目.bat`。
3. 等待命令窗口完成离线依赖安装和健康检查。
4. 浏览器自动打开 `http://127.0.0.1:8000/`。

也可以在命令提示符（CMD）中运行：

```bat
start-dev.cmd
```

轻量源码包不需要 Node.js、npm、PowerShell、Rust、Cargo、管理员权限或首次联网安装。启动器使用包内 wheelhouse 创建 Python 虚拟环境，并在一个 Uvicorn 进程中同时提供前端和 API。默认端口 8000 被占用时，会自动选择 8001–8010 中第一个可用端口并显示实际地址。

停止程序时，在启动窗口按 `Ctrl+C`。不要在数据库写入过程中强制关闭窗口。

### 轻量版能力边界

轻量源码包用于源码审查和基础演示，可以完成本地规则模式下的文字输入主流程，包括会议创建、会前简报、会议发言、超权确认、纪要/行动项、ADS 写回和审计查看。

本地语音组件未随轻量源码包提供：其中不包含 FFmpeg、`faster-whisper`、说话人分离运行时或语音模型。页面应如实显示语音组件不可用；演示时继续使用文字输入即可。

本机已优先支持 **Python 3.13 x64** 的可选“一键配置语音”：启动产品后，在首次启动页或 `设置 → 本地语音` 点击按钮，程序才会联网安装依赖和下载约 800 MB 语音资源。配置结束后手动重启 ADS。Python 3.11、3.12、3.14 仍按轻量文字模式支持，完整语音未逐版验收；需要尝试时按照[轻量源码版升级完整语音说明](docs/guides/轻量源码版升级完整语音说明.md)手动操作。

## 完整 Windows 发行版

电脑没有兼容 Python，或需要随包提供的 FFmpeg、本地转写和说话人分离能力时，请使用 [GitHub Releases 完整 Windows x64 发行版](https://github.com/yexianglun537-glitch/ads-meeting-agent/releases)。

完整发行版解压后运行 `ADS会议智能体.exe`，无需预装 Python、Node.js、Git、FFmpeg 或 Whisper。发布前仍需核对具体版本的文件大小、SHA-256 和发行说明。

## 模型配置

本地配置位于 `backend/.env`。默认 `USE_MOCK_AI=true`，会议分析使用本地规则模式，不需要 API Key。切换在线模型时可改为：

```env
USE_MOCK_AI=false
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

也可以在产品的 `设置 → 模型服务` 中配置 DeepSeek 或 OpenAI-compatible 模型。DeepSeek 常用服务地址是 `https://api.deepseek.com`，模型名称可填写 `deepseek-chat`；其他 OpenAI 兼容服务必须使用对应服务商提供的 API 根地址和模型名称。保存后先点“测试连接”，再提交一条会议发言，并在“模型调用审计”确认实际 Provider。API Key 只保存在本地后端，不应写入前端、文档或版本库。

Whisper 只负责语音转文字，不负责会议分析和代理回复；在线 AI 模型与本地语音是两套独立配置。

## 数据与运行文件

轻量源码包和完整 Windows 发行版运行后，数据库、音频、备份和日志写入解压目录下的 `data/` 与 `logs/`。生成的 `.env` 和 `.venv` 位于 `backend/`。这些运行文件、密钥和真实业务数据不得重新放入提交 ZIP 或公开仓库。

## 开发维护

以下命令仅供开发维护人员使用，不是评委运行轻量源码包的步骤。开发模式需要 Node.js，并使用前端 5173、后端 8000 两个端口。

```powershell
Set-Location frontend
npm ci
npm run dev -- --host 127.0.0.1
```

另开终端启动后端：

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

维护者生成完整发行版：

```powershell
.\packaging\build-release.ps1 -Version 0.1.0
```

## 验证

```powershell
Set-Location frontend
npm test
npm run typecheck
npm run build

Set-Location ..\backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

## 核心文档

- [当前产品需求与验收标准](docs/requirements/ADS会议智能体当前产品需求与验收标准.md)
- [源码包兼容性交付要求](docs/requirements/2026-08-31-源码包兼容性交付要求.md)
- [ADS 会议智能体使用教程](docs/guides/ADS会议智能体使用教程.md)
- [轻量源码版升级完整语音说明](docs/guides/轻量源码版升级完整语音说明.md)
- [本地语音转文字工具需求](docs/requirements/ADS会议智能体本地语音转文字工具需求文档.md)
- [ADS 核心 Prompt 与工作流说明](docs/ADS核心Prompt与工作流说明.md)

第三方组件来源和许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
