from app.models import ProviderDefinition


PROVIDER_REGISTRY = [
    ProviderDefinition(vendor_id="deepseek", name="DeepSeek", adapter_type="deepseek", default_base_url="https://api.deepseek.com/v1", default_model="deepseek-chat"),
    ProviderDefinition(vendor_id="qwen", name="阿里云百炼 / 通义千问", adapter_type="openai_compatible", default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", default_model="qwen-plus"),
    ProviderDefinition(vendor_id="doubao", name="火山方舟 / 豆包", adapter_type="openai_compatible", default_base_url="https://ark.cn-beijing.volces.com/api/v3", default_model="doubao-seed-1-6-250615"),
    ProviderDefinition(vendor_id="moonshot", name="Moonshot / Kimi", adapter_type="openai_compatible", default_base_url="https://api.moonshot.cn/v1", default_model="moonshot-v1-32k"),
    ProviderDefinition(vendor_id="zhipu", name="智谱 GLM", adapter_type="openai_compatible", default_base_url="https://open.bigmodel.cn/api/paas/v4", default_model="glm-4.5"),
    ProviderDefinition(vendor_id="hunyuan", name="腾讯混元", adapter_type="openai_compatible", default_base_url="https://api.hunyuan.cloud.tencent.com/v1", default_model="hunyuan-turbos-latest"),
    ProviderDefinition(vendor_id="spark", name="讯飞星火", adapter_type="openai_compatible", default_base_url="https://spark-api-open.xf-yun.com/v1", default_model="generalv3.5"),
    ProviderDefinition(vendor_id="qianfan", name="百度千帆 / 文心", adapter_type="openai_compatible", default_base_url="https://qianfan.baidubce.com/v2", default_model="ernie-4.5-turbo-128k"),
    ProviderDefinition(vendor_id="minimax", name="MiniMax", adapter_type="openai_compatible", default_base_url="https://api.minimax.chat/v1", default_model="MiniMax-Text-01"),
    ProviderDefinition(vendor_id="stepfun", name="阶跃星辰 StepFun", adapter_type="openai_compatible", default_base_url="https://api.stepfun.com/v1", default_model="step-2-16k"),
    ProviderDefinition(vendor_id="baichuan", name="百川智能", adapter_type="openai_compatible", default_base_url="https://api.baichuan-ai.com/v1", default_model="Baichuan4-Turbo"),
    ProviderDefinition(vendor_id="yi", name="零一万物 Yi", adapter_type="openai_compatible", default_base_url="https://api.lingyiwanwu.com/v1", default_model="yi-lightning"),
    ProviderDefinition(vendor_id="generic", name="其他 OpenAI-compatible 服务", adapter_type="openai_compatible", default_base_url="https://api.openai.com/v1", default_model="gpt-4.1-mini"),
]


def provider_definition(vendor_id: str) -> ProviderDefinition | None:
    return next((item for item in PROVIDER_REGISTRY if item.vendor_id == vendor_id), None)
