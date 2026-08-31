# Git 提交说明草稿

> 状态：仅供任务 6 最终验证通过后使用。当前不得据此宣称已提交或已推送。

## 建议提交标题

```text
feat: add offline-compatible Windows source package
```

## 建议提交正文

```text
- lock lightweight FastAPI dependencies for Python 3.11-3.14
- bundle Windows x64 wheels for fully offline installation
- include the verified Vite production build in the source package
- replace the Node/Vite runtime with a CMD and single Uvicorn launcher
- add health-gated browser launch and automatic port fallback
- document the lightweight speech boundary and GitHub release fallback
```

## 提交前文件范围

应包含本次兼容性改造相关文件：

- `backend/requirements-core.txt`
- `backend/requirements.txt`
- `backend/tests/test_source_compatibility_contract.py`
- `frontend/dist` 由打包时生成，不提交时以仓库规则为准
- `packaging/build-source-package.ps1`
- `packaging/launcher.py`
- `start-dev.cmd`
- `启动项目.bat`（若内容未变，只需确认调用关系）
- `README.md`
- `docs/README.md`
- `docs/guides/ADS会议智能体使用教程.md`
- `docs/requirements/2026-08-31-源码包兼容性交付要求.md`

不得误提交：

- `.env`、数据库、密钥、日志、音频、备份、模型；
- `.venv`、`node_modules`；
- `.tmp` 临时验收目录和临时 ZIP；
- 与本次任务无关的用户文档或脚本。

## 提交前证据

```text
backend tests: PASS, 78 passed
frontend tests: PASS, 49 passed
typecheck/build: PASS / PASS
source ZIP size: 10,795,014 bytes (10.29 MiB)
source ZIP SHA-256: C48EBDD45BEDC32AE6593F7870D62BC9DF2140AFAA5984B774470F5D889FD238
isolated startup: PASS on Python 3.13.12 x64, Chinese and spaced path, fully offline install
port fallback: PASS, occupied 8000 and ADS selected 8001
Python matrix: cp311/cp312/cp313/cp314 wheel resolution PASS; full startup PASS on 3.13 only; 3.11/3.12/3.14 unverified
```

## 推送前确认

- [x] `git status` 中只暂存本次任务文件；
- [x] `git diff --cached --check` 通过；
- [x] 正式 ZIP 已独立验证；
- [ ] 提交创建成功；
- [ ] 推送到 `https://github.com/yexianglun537-glitch/ads-meeting-agent` 成功；
- [ ] GitHub 页面可看到最新提交。
