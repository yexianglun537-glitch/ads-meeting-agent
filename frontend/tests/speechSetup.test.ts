import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const onboarding = source.slice(source.indexOf("function Onboarding("), source.indexOf("function Sidebar("));
const settings = source.slice(source.indexOf("function SettingsView("), source.indexOf("function MetricBaselinePanel("));

test("onboarding keeps the speech setup action beside local speech status", () => {
  assert.match(onboarding, /readiness-action/);
  assert.match(onboarding, /一键配置语音/);
  assert.match(onboarding, /onStartSpeechSetup/);
  assert.match(styles, /\.readiness-action/);
});

test("settings explains local 3.13 support and manual fallback", () => {
  assert.match(settings, /Python 3\.13 x64/);
  assert.match(settings, /手动配置教程/);
  assert.match(settings, /重启 ADS/);
  assert.match(settings, /speech-setup-progress/);
});

test("online AI help separates speech recognition from meeting analysis", () => {
  assert.match(settings, /DeepSeek/);
  assert.match(settings, /OpenAI 兼容/);
  assert.match(settings, /Whisper 只负责语音转文字/);
  assert.match(settings, /USE_MOCK_AI=false/);
});
