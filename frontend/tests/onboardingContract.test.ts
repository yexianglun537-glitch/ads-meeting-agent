import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const onboarding = source.slice(source.indexOf("function Onboarding("), source.indexOf("function Sidebar("));

test("first-run setup does not ask for a model or API key", () => {
  assert.doesNotMatch(onboarding, /首次使用的会议模型/);
  assert.doesNotMatch(onboarding, /API Key/);
  assert.doesNotMatch(onboarding, /props\.models/);
});

test("successful onboarding opens the agent center for identity review", () => {
  assert.match(source, /await refreshAll\(\);\s*setView\("agents"\);/);
  assert.match(source, /已构建您的 AI 分身，请检查并调整/);
  assert.match(onboarding, /完成配置并检查 AI 分身/);
});
