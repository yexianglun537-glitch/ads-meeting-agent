export type ModelRuntimeConfig = {
  provider_id: string;
  adapter_type: "deepseek" | "openai_compatible" | "mock";
  enabled: boolean;
  is_default: boolean;
  configured: boolean;
  connection_status: "not_configured" | "untested" | "ok" | "failed" | "mock";
};

export type AiRuntimeLike = {
  mode: "mock" | "live";
  label: string;
  message: string;
};

export type ModelRuntimeState = {
  runnable: boolean;
  label: "当前可运行" | "当前未使用" | "未启用" | "未配置" | "连接未就绪" | "正在确认";
  reason: string;
};

export function getModelRuntimeState(model: ModelRuntimeConfig, runtime: AiRuntimeLike | null): ModelRuntimeState {
  if (!model.enabled) return { runnable: false, label: "未启用", reason: "该模型已关闭，不会出现在会议模型列表中。" };
  if (model.adapter_type === "mock") {
    return { runnable: true, label: "当前可运行", reason: "本地规则无需在线连接，可随时用于会议。" };
  }
  if (!runtime) return { runnable: false, label: "正在确认", reason: "正在读取当前实际运行模式。" };
  if (runtime.mode === "mock") {
    return { runnable: false, label: "当前未使用", reason: "全局处于本地规则模式，会议不会调用此在线模型。" };
  }
  if (!model.configured) return { runnable: false, label: "未配置", reason: "请先保存 API Key，再测试连接。" };
  if (model.connection_status !== "ok") {
    return { runnable: false, label: "连接未就绪", reason: "最近连接测试未通过，暂不用于会议。" };
  }
  return { runnable: true, label: "当前可运行", reason: "全局处于在线模式，会议可以调用此模型。" };
}

export function getRunnableModels<T extends ModelRuntimeConfig>(models: T[], runtime: AiRuntimeLike | null): T[] {
  return models.filter((model) => getModelRuntimeState(model, runtime).runnable);
}

export function getRunnableModelId(models: ModelRuntimeConfig[], runtime: AiRuntimeLike | null, selectedId: string): string {
  const runnableModels = getRunnableModels(models, runtime);
  if (runnableModels.some((model) => model.provider_id === selectedId)) return selectedId;
  return runnableModels.find((model) => model.is_default)?.provider_id ?? runnableModels[0]?.provider_id ?? "";
}
