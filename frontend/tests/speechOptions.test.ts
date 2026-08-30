import assert from "node:assert/strict";
import test from "node:test";

import {
  appendDiarizationOptions,
  isSpeechJobActive,
  speechModelLabel,
  speechProgressLabel,
  speechStatus,
} from "../src/speechOptions.ts";


test("adds enabled automatic speaker diarization to an audio upload", () => {
  const form = new FormData();

  appendDiarizationOptions(form, { diarizationEnabled: true, speakerCount: null });

  assert.equal(form.get("diarization_enabled"), "true");
  assert.equal(form.has("speaker_count"), false);
});


test("adds a fixed speaker count only when selected", () => {
  const form = new FormData();

  appendDiarizationOptions(form, { diarizationEnabled: true, speakerCount: 4 });

  assert.equal(form.get("speaker_count"), "4");
});


test("treats speaker diarization as an active visible job stage", () => {
  assert.equal(isSpeechJobActive("diarizing"), true);
  assert.equal(speechStatus("diarizing"), "区分发言人");
  assert.equal(speechProgressLabel("diarizing"), "正在区分发言人");
});


test("hides legacy absolute paths when displaying the bundled speech model", () => {
  assert.equal(
    speechModelLabel("C:\\old-release\\backend\\data\\models\\faster-whisper-small"),
    "faster-whisper-small",
  );
  assert.equal(speechModelLabel("custom-whisper-model"), "custom-whisper-model");
});
