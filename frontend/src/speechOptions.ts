export type SpeechJobStatus = "uploaded" | "preprocessing" | "transcribing" | "diarizing" | "awaiting_review" | "confirmed" | "failed" | "cancelled";

export type DiarizationOptions = {
  diarizationEnabled: boolean;
  speakerCount: number | null;
};

export function appendDiarizationOptions(form: FormData, options: DiarizationOptions) {
  form.append("diarization_enabled", String(options.diarizationEnabled));
  if (options.speakerCount !== null) form.append("speaker_count", String(options.speakerCount));
}

export function isSpeechJobActive(status: SpeechJobStatus) {
  return ["uploaded", "preprocessing", "transcribing", "diarizing"].includes(status);
}

export function speechModelLabel(modelName: string) {
  return modelName.includes("faster-whisper-small") ? "faster-whisper-small" : modelName;
}

export function speechStatus(status: SpeechJobStatus) {
  return ({
    uploaded: "已上传",
    preprocessing: "预处理",
    transcribing: "转写中",
    diarizing: "区分发言人",
    awaiting_review: "待审核",
    confirmed: "已确认",
    failed: "失败",
    cancelled: "已取消",
  } as const)[status];
}

export function speechProgressLabel(status: SpeechJobStatus) {
  return ({
    uploaded: "排队中",
    preprocessing: "音频预处理",
    transcribing: "本地转写",
    diarizing: "正在区分发言人",
    awaiting_review: "等待审核",
    confirmed: "已确认",
    failed: "处理失败",
    cancelled: "已取消",
  } as const)[status];
}
