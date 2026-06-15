// cinema-config.js — 配置页面构建、保存、测试与渲染

var SEARCH_TYPE_MAP = {
  zhipu: [
    { value: "search_std", label: "标准搜索" },
    { value: "search_pro", label: "增强搜索" },
  ],
  qwen: [
    { value: "enable_search", label: "标准搜索" },
    { value: "forced_search", label: "强制搜索" },
  ],
  moonshot: [{ value: "web_search", label: "联网搜索" }],
};
var PROVIDER_BASE_URL_MAP = {
  zhipu: "https://open.bigmodel.cn/api/paas/v4",
  qwen: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  moonshot: "https://api.moonshot.cn/v1",
};
var PROVIDER_MODEL_MAP = {
  zhipu: [
    { value: "glm-4-flash", label: "GLM-4-Flash" },
    { value: "glm-4-air", label: "GLM-4-Air" },
    { value: "glm-4-plus", label: "GLM-4-Plus" },
  ],
  qwen: [
    { value: "qwen-plus", label: "Qwen-Plus" },
    { value: "qwen-max", label: "Qwen-Max" },
    { value: "qwen-turbo", label: "Qwen-Turbo" },
  ],
  moonshot: [
    { value: "moonshot-v1-8k", label: "Moonshot v1 8K" },
    { value: "moonshot-v1-32k", label: "Moonshot v1 32K" },
  ],
};



