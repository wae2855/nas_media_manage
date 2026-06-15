// cinema-app-events.js - bindEvents
function bindEvents() {
  document.addEventListener("click", (event) => {
    const nav = event.target.closest("[data-nav]");
    if (nav) {
      setView(nav.dataset.viewTarget || nav.dataset.nav, nav.dataset.nav);
      if (nav.dataset.taskFilter) setTaskFilter(nav.dataset.taskFilter);
    }
    const taskFilterChip = event.target.closest("[data-task-filter-chip]");
    if (taskFilterChip) setTaskFilter(taskFilterChip.dataset.taskFilterChip);
    const configStage = event.target.closest("[data-config-stage]");
    if (configStage) setConfigStage(configStage.dataset.configStage);
    const stageJump = event.target.closest("[data-config-stage-jump]");
    if (stageJump) setConfigStage(stageJump.dataset.configStageJump);
    const cleanerTab = event.target.closest("[data-cleaner-tab]");
    if (cleanerTab) setCleanerTab(cleanerTab.dataset.cleanerTab);
    const varGroup = event.target.closest("[data-var-group]");
    if (varGroup) toggleVarGroup(varGroup.dataset.varGroup);
    const advancedDisclosure = event.target.closest(
      "[data-advanced-disclosure]",
    );
    if (advancedDisclosure)
      toggleAdvancedDisclosure(advancedDisclosure.dataset.advancedDisclosure);
    if (event.target.closest("#btn-match-preview")) {
      runConfigSimulator();
      return;
    }
    const matchTraceAction = event.target.closest(
      '[data-match-trace-action="open"]',
    );
    if (matchTraceAction) {
      const trace = matchTraceAction.dataset.trace;
      const filename = matchTraceAction.dataset.filename || "";
      if (trace && typeof showMatchTraceModal === "function") {
        showMatchTraceModal(JSON.parse(trace), filename);
      }
      return;
    }
    const ruleAction = event.target.closest("[data-rule-action]");
    if (ruleAction) {
      const index = Number(ruleAction.dataset.ruleIndex || -1);
      if (ruleAction.dataset.ruleAction === "add") openRuleEditor();
      if (ruleAction.dataset.ruleAction === "edit") openRuleEditor(index);
      if (ruleAction.dataset.ruleAction === "delete") deleteInlineRule(index);
      return;
    }
    const taskAction = event.target.closest("[data-task-action]");
    if (taskAction) {
      performTaskAction(
        taskAction.dataset.taskAction,
        taskAction.dataset.taskId || "",
      );
      return;
    }
    const taskSelect = event.target.closest("[data-task-select]");
    if (taskSelect) {
      toggleTaskSelect(taskSelect.dataset.taskSelect);
      return;
    }
    const taskRowOpen = event.target.closest("[data-task-row-open]");
    if (
      taskRowOpen &&
      !event.target.closest("button, input, a, select, textarea")
    ) {
      openTaskDetail(taskRowOpen.dataset.taskRowOpen || "");
      return;
    }
    const taskRow = event.target.closest("[data-task-row]");
    if (
      taskRow &&
      !event.target.closest("button, input, a, select, textarea")
    ) {
      toggleTaskSelect(taskRow.dataset.taskRow || "");
      return;
    }
    const batchTaskAction = event.target.closest("[data-batch-task-action]");
    if (batchTaskAction) {
      performBatchTaskAction(batchTaskAction.dataset.batchTaskAction);
      return;
    }
    const recycleAction = event.target.closest("[data-recycle-action]");
    if (recycleAction) {
      performRecycleAction(
        recycleAction.dataset.recycleAction,
        recycleAction.dataset.recycleId || "",
      );
      return;
    }
    const recycleSelect = event.target.closest("[data-recycle-select]");
    if (recycleSelect) {
      toggleRecycleSelect(recycleSelect.dataset.recycleSelect);
      return;
    }
    const batchRecycleAction = event.target.closest(
      "[data-batch-recycle-action]",
    );
    if (batchRecycleAction) {
      performBatchRecycleAction(batchRecycleAction.dataset.batchRecycleAction);
      return;
    }
    const providerAction = event.target.closest("[data-provider-action]");
    if (providerAction) {
      const providerType = providerAction.dataset.providerType || "";
      const actionMap = {
        save: () => saveProvidersConfig(providerType),
        test: () => testProviderConnection(providerType),
        preview: () => previewProvider(providerType),
      };
      const handler = actionMap[providerAction.dataset.providerAction];
      if (handler) handler();
      return;
    }
    const configSave = event.target.closest("[data-config-save]");
    if (configSave) {
      const actionMap = {
        source: saveSourceConfig,
        temp: saveTempConfig,
        recycle: saveRecycleConfig,
        rules: saveRulesConfig,
        scrape: () => saveProvidersConfig(""),
        ai: saveLlmConfig,
        // T2.10 后：每个 tab 独立保存（key 用下划线与配置 section 名一致）
        ai_assist: saveAiAssistConfig,
        ai_search: saveAiScrapeConfig,
        // 向后兼容老 key（连字符形式，当前 HTML 已不使用）
        "ai-assist": saveAiAssistConfig,
        "ai-scrape": saveAiScrapeConfig,
        "ai-prompts": saveAiPromptsConfig,
        "ai-scene-strategy": saveAiSceneStrategyConfig,
        naming: saveImportOptionsConfig,
        security: saveSecurityConfig,
        hermes: saveHermesConfig,
        system: saveAdvancedSystemConfig,
      };
      const handler = actionMap[configSave.dataset.configSave];
      if (handler) handler();
      return;
    }
    const pathTest = event.target.closest("[data-path-test]");
    if (pathTest) {
      testConfigPath(pathTest.dataset.pathTest);
      return;
    }
    const rulesTest = event.target.closest("[data-rules-test]");
    if (rulesTest) {
      testAllRulePermissions();
      return;
    }
    const llmTest = event.target.closest("[data-llm-test]");
    if (llmTest) {
      testLlmConnection(llmTest);
      return;
    }
    const collapseToggle = event.target.closest("[data-collapse-toggle]");
    if (collapseToggle) {
      if (event.target.closest("input, .toggle-pill, label.toggle-pill"))
        return;
      const bodyId = collapseToggle.dataset.collapseToggle;
      const body = document.getElementById(bodyId);
      const card = collapseToggle.closest(".config-collapse-card");
      if (body && card) {
        card.classList.toggle("open");
      }
      return;
    }
    const hermesTest = event.target.closest("[data-hermes-test]");
    if (hermesTest) {
      testHermesConnection();
      return;
    }
    const demoScenario = event.target.closest("[data-demo-scenario]");
    if (demoScenario) {
      const scenario = demoScenario.dataset.demoScenario;
      const demoFile = demoScenario.dataset.demoFile;
      if (scenario === "scrape" || scenario === "series_scrape") {
        runAiScrapeDemo(scenario, demoFile);
      } else {
        runAiAssistDemo(scenario, demoFile);
      }
      return;
    }
    if (event.target.closest("#btn-ai-scrape-demo")) {
      openAiScrapeDemoModal();
      return;
    }
    if (event.target.closest("#btn-ai-scrape-demo-close")) {
      closeAiScrapeDemoModal();
      return;
    }
    if (
      event.target.closest("#ai-scrape-demo-modal") &&
      !event.target.closest(".ai-demo-modal-content")
    ) {
      closeAiScrapeDemoModal();
      return;
    }
    if (event.target.closest("#btn-ai-assist-demo")) {
      openAiAssistDemoModal();
      return;
    }
    if (event.target.closest("#btn-ai-assist-demo-close")) {
      closeAiAssistDemoModal();
      return;
    }
    if (
      event.target.closest("#ai-assist-demo-modal") &&
      !event.target.closest(".ai-demo-modal-content")
    ) {
      closeAiAssistDemoModal();
      return;
    }
    const action = event.target.closest("[data-action]");
    if (action) runAction(action.dataset.action, action);
    const detailToggleBtn = event.target.closest("#tmdb-detail-toggle-btn");
    if (detailToggleBtn) {
      const structured = document.getElementById("tmdb-detail-structured");
      const raw = document.getElementById("tmdb-detail-raw");
      if (structured && raw) {
        if (raw.style.display === "none") {
          raw.style.display = "block";
          structured.style.display = "none";
          detailToggleBtn.textContent = "查看结构化";
        } else {
          raw.style.display = "none";
          structured.style.display = "block";
          detailToggleBtn.textContent = "查看原始 JSON";
        }
      }
      return;
    }
    const detailGroupHeader = event.target.closest(".tmdb-detail-group-header");
    if (detailGroupHeader) {
      detailGroupHeader.parentElement.classList.toggle("collapsed");
      return;
    }
  });
  document.addEventListener("input", (event) => {
    if (event.target.id === "task-rename-input")
      updateRenamePreview(event.target);
    if (
      event.target.id?.startsWith("cfg-ai_assist-") ||
      event.target.id?.startsWith("cfg-ai_search-")
    ) {
      updateAiConfigStatus();
    }
  });
  document.addEventListener("change", (event) => {
    const taskSelectAll = event.target.closest("[data-task-select-all]");
    if (taskSelectAll) {
      selectAllVisibleTasks();
      return;
    }
    const recycleSelectAll = event.target.closest("[data-recycle-select-all]");
    if (recycleSelectAll) {
      selectAllVisibleRecycle();
      return;
    }
    const providerToggle = event.target.closest("[data-provider-toggle]");
    if (!providerToggle) return;
    const card = providerToggle.closest("[data-provider-card]");
    if (card) card.classList.toggle("is-disabled", !providerToggle.checked);
  });
  document
    .getElementById("cfg-source-cleaner-enabled-inline")
    .addEventListener("change", toggleSourceCleanerUi);
  document
    .getElementById("cfg-source_cleaner-ai_enabled-inline")
    .addEventListener("change", toggleSourceCleanerUi);
  document
    .getElementById("cfg-source-recursive-toggle-inline")
    .addEventListener("change", toggleSourceDepthField);
  const watcherToggle = document.getElementById(
    "cfg-file_watcher-enabled-inline",
  );
  if (watcherToggle)
    watcherToggle.addEventListener("change", toggleFileWatcherPollGroup);
  const hermesToggle = document.getElementById("cfg-hermes_enabled-inline");
  if (hermesToggle)
    hermesToggle.addEventListener("change", toggleHermesInlineFields);
  window.addEventListener("scroll", updateStickyHeroState, { passive: true });
  window.addEventListener("resize", updateStickyHeroState);
  toggleSourceCleanerUi();
  toggleSourceDepthField();
  toggleHermesInlineFields();
}
