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
  const feedback = document.getElementById("llm-test-result");

  const showFeedback = (state, message) => {
    if (!feedback) return;
    const titles = {
      testing: "正在测试",
      success: "连接成功",
      error: "连接失败",
    };
    feedback.hidden = false;
    feedback.className = `llm-test-result is-${state}`;
    feedback.innerHTML = `<b>${escapeHtml(titles[state] || "测试结果")}</b><span>${escapeHtml(message)}</span>`;
  };

  if (!baseUrl) {
    showFeedback("error", "请先填写 LLM API 地址，再重新测试。");
    return;
  }
  if (!model) {
    showFeedback("error", "请先填写模型 ID，再重新测试。");
    return;
  }
  const originalLabel = triggerEl?.textContent || "测试连通性";
  if (triggerEl) {
    triggerEl.disabled = true;
    triggerEl.textContent = "正在测试...";
  }
  showFeedback("testing", "正在联系 LLM 服务，请稍候。");
  try {
    const result = await requestApi("POST", "/config/test-llm", {
      api_key: apiKey,
      base_url: baseUrl,
      model: model,
    });
    const data = result.data || {};
    const success = result.code === 200 && data.success === true;
    const message =
      data.message ||
      result.message ||
      (success ? "当前地址、模型和密钥可以正常使用。" : "未能连接 LLM 服务，请检查配置后重试。");
    showFeedback(success ? "success" : "error", message);
  } catch (error) {
    showFeedback("error", error?.message || "测试请求失败，请检查网络后重试。");
  } finally {
    if (triggerEl) {
      triggerEl.disabled = false;
      triggerEl.textContent = originalLabel;
    }
  }
}
