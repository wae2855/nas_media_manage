// LLM 配置交互（ADR-0010：AI 刮削移除后仅保留连通性测试，llm 块为唯一配置源）

async function testLlmConnection(triggerEl) {
  const baseUrl = String(
    document.getElementById("cfg-llm-base_url")?.value || "",
  ).trim();
  const model = String(
    document.getElementById("cfg-llm-model")?.value || "",
  ).trim();
  const apiKey = String(
    document.getElementById("cfg-llm-api_key")?.value || "",
  ).trim();

  if (!baseUrl) {
    showToast("请先填写 LLM API 地址");
    return;
  }
  if (!model) {
    showToast("请先填写模型 ID");
    return;
  }
  showToast("正在测试 LLM 连通性...");
  const result = await requestApi("POST", "/config/test-llm", {
    api_key: apiKey,
    base_url: baseUrl,
    model: model,
  });
  const data = result.data || {};
  showToast(data.message || result.message || "LLM 测试已完成");
}
