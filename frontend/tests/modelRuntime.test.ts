import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  getModelRuntimeState,
  getRunnableModelId,
  getRunnableModels,
  type AiRuntimeLike,
  type ModelRuntimeConfig,
} from "../src/modelRuntime.ts";

const mainSource = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

const mockRuntime: AiRuntimeLike = {
  mode: "mock",
  label: "本地规则模式",
  message: "当前会议分析使用本地规则，不调用在线大模型。",
};
const liveRuntime: AiRuntimeLike = {
  mode: "live",
  label: "在线模型",
  message: "当前会议分析将使用所选在线模型。",
};

const models: ModelRuntimeConfig[] = [
  { provider_id: "deepseek", adapter_type: "deepseek", enabled: true, is_default: true, configured: true, connection_status: "ok" },
  { provider_id: "not-configured", adapter_type: "openai_compatible", enabled: true, is_default: false, configured: false, connection_status: "not_configured" },
  { provider_id: "failed", adapter_type: "openai_compatible", enabled: true, is_default: false, configured: true, connection_status: "failed" },
  { provider_id: "untested", adapter_type: "openai_compatible", enabled: true, is_default: false, configured: true, connection_status: "untested" },
  { provider_id: "disabled", adapter_type: "openai_compatible", enabled: false, is_default: false, configured: true, connection_status: "ok" },
  { provider_id: "mock", adapter_type: "mock", enabled: true, is_default: false, configured: true, connection_status: "mock" },
];

test("model runtime: mock mode exposes only the enabled local-rules model", () => {
  assert.deepEqual(getRunnableModels(models, mockRuntime).map((item) => item.provider_id), ["mock"]);
});

test("model runtime: live mode excludes online models that are not ready", () => {
  assert.deepEqual(getRunnableModels(models, liveRuntime).map((item) => item.provider_id), ["deepseek", "mock"]);
});

test("model runtime: invalid current or default selection falls back to a runnable model", () => {
  assert.equal(getRunnableModelId(models, mockRuntime, "deepseek"), "mock");
  assert.equal(getRunnableModelId(models, liveRuntime, "mock"), "mock");
  assert.equal(getRunnableModelId(models, liveRuntime, "missing"), "deepseek");
  assert.equal(getRunnableModelId(models.map((model) => ({ ...model, enabled: false })), liveRuntime, "deepseek"), "");
});

test("model runtime: settings distinguish connection history from current runtime", () => {
  assert.deepEqual(getModelRuntimeState(models[0], mockRuntime), {
    runnable: false,
    label: "当前未使用",
    reason: "全局处于本地规则模式，会议不会调用此在线模型。",
  });
  assert.equal(getModelRuntimeState(models[0], liveRuntime).label, "当前可运行");
  assert.equal(getModelRuntimeState(models[1], liveRuntime).label, "未配置");
});

test("all model surfaces use the shared runtime decision", () => {
  const createStart = mainSource.indexOf("function CreateMeeting(");
  const createEnd = mainSource.indexOf("type MeetingTab", createStart);
  const createMeetingSource = mainSource.slice(createStart, createEnd);

  assert.match(mainSource, /getRunnableModels/);
  assert.match(mainSource, /当前可运行模型/);
  assert.match(mainSource, /当前实际运行/);
  assert.doesNotMatch(createMeetingSource, /models\.filter\(\(model\) => model\.enabled\)/);
});
