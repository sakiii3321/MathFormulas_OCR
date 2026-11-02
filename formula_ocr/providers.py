"""Official endpoints verified against provider documentation on 2026-10-31."""
PROVIDERS = {
    "OpenAI 官方": ("https://api.openai.com/v1", "", "填写账户可用的视觉模型 ID。使用官方 Chat Completions 图像接口。"),
    "硅基流动": ("https://api.siliconflow.cn/v1", "", "在硅基流动模型广场选择视觉模型，填写完整 ID（包含组织前缀）。"),
    "DeepSeek 官方": ("https://api.deepseek.com", "deepseek-flash", "官方视觉文档支持 deepseek-flash 图像输入；其他模型请先确认视觉能力。"),
    "自定义兼容接口": ("", "", "填写完整 Base URL 和视觉模型名称；支持本机 OpenAI 兼容服务。"),
}
