import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

test("does not infer the current meeting from API order", () => {
  assert.doesNotMatch(source, /meetings\.find\([^\n]+\) \?\? meetings\[0\]/);
  assert.doesNotMatch(source, /if \(!activeMeetingId && presentable\[0\]\) setActiveMeetingId\(presentable\[0\]\.id\)/);
});

test("exposes an explicit global current-meeting selector", () => {
  assert.match(source, />当前会议</);
  assert.match(source, />选择当前会议</);
  assert.match(source, /<MeetingSelection/);
});

test("protects unsent text when switching meetings", () => {
  assert.match(source, /transcript\.trim\(\)/);
  assert.match(source, /未提交文字/);
  assert.match(source, /setTranscript\(""\)/);
});
