// config-save.js - save sections, test paths, permissions
async function saveSection(sectionName) {
  var builder = _sectionBuilders[sectionName];
  if (!builder) {
    showToast("未知的配置区块: " + sectionName, "error");
    return;
  }

  var data = builder();

  if (sectionName === "basic") {
    var sourceDir = (data.source_dir || "").replace(/\/+$/, "");
    var tempDir = (data.temp_dir || "").replace(/\/+$/, "");
    var recycleDir = (
      (data.source_policy &&
        (data.source_policy.recycle_dir ||
          data.source_policy.quarantine_dir)) ||
      ""
    ).replace(/\/+$/, "");

    var missing = [];
    if (!sourceDir) missing.push("源目录");
    if (!tempDir) missing.push("中转目录");
    if (!recycleDir) missing.push("回收站路径");
    if (missing.length > 0) {
      showToast(missing.join("、") + " 为必填项", "error");
      return;
    }

    var conflicts = [];
    if (sourceDir && tempDir && sourceDir === tempDir)
      conflicts.push("源目录与中转目录不能相同");
    if (sourceDir && recycleDir && sourceDir === recycleDir)
      conflicts.push("源目录与回收站目录不能相同");
    if (tempDir && recycleDir && tempDir === recycleDir)
      conflicts.push("中转目录与回收站目录不能相同");
    if (conflicts.length > 0) {
      showToast(conflicts.join("；"), "error");
      return;
    }
  }

  if (sectionName === "basic") {
    showToast("正在检查路径权限...", "info");
    var permCheck = await apiRequest("POST", "/config/check-permission", {
      source_dir: data.source_dir,
      temp_dir: data.temp_dir,
      log_dir: currentConfig.log_dir || "",
      path_rules: currentConfig.path_rules || [],
    });
    if (permCheck && permCheck.code === 200 && permCheck.data) {
      if (!permCheck.data.all_ok) {
        showPermissionDialog(permCheck.data.issues || []);
        return;
      }
    } else {
      showToast("权限检查接口异常，但仍可尝试保存", "warning");
    }
  }

  if (sectionName === "path_rules") {
    showToast("正在检查入库目录权限...", "info");
    var permCheck2 = await apiRequest("POST", "/config/check-permission", {
      source_dir: "",
      temp_dir: "",
      log_dir: "",
      path_rules: data.path_rules || [],
    });
    if (permCheck2 && permCheck2.code === 200 && permCheck2.data) {
      if (!permCheck2.data.all_ok) {
        showPermissionDialog(permCheck2.data.issues || []);
        return;
      }
    }
    if (data._uncheckedRules && data._uncheckedRules.length > 0) {
      var ruleList = data._uncheckedRules.join("、");
      if (
        !confirm(
          "规则 #" +
            ruleList +
            ' 未设置任何维度条件，将匹配所有文件。\n\n如果这是兜底规则请确认保存，否则建议回到页面设置维度条件后再保存。\n\n点击"确定"保存，点击"取消"返回修改。',
        )
      ) {
        return;
      }
    }
  }

  if (sectionName === "source_cleaner") {
    var cleanerData = data.source_cleaner || data;
    if (cleanerData.enabled) {
      showToast("正在检查路径权限...", "info");
      var sourceDir = currentConfig.source_dir || "";
      var recycleDir = (currentConfig.source_policy || {}).recycle_dir || "";
      var permIssues = [];
      if (sourceDir) {
        var srcPerm = await apiRequest("POST", "/path/test", {
          path: sourceDir,
          need_write: true,
        });
        if (!srcPerm || !srcPerm.data || !srcPerm.data.ok) {
          permIssues.push({
            field: "source_dir",
            path: sourceDir,
            message:
              (srcPerm && srcPerm.data && srcPerm.data.message) ||
              "源目录无写权限",
          });
        }
      }
      if (recycleDir) {
        var rclPerm = await apiRequest("POST", "/path/test", {
          path: recycleDir,
          need_write: true,
        });
        if (!rclPerm || !rclPerm.data || !rclPerm.data.ok) {
          permIssues.push({
            field: "recycle_dir",
            path: recycleDir,
            message:
              (rclPerm && rclPerm.data && rclPerm.data.message) ||
              "回收站目录无写权限",
          });
        }
      }
      if (permIssues.length > 0) {
        showPermissionDialog(permIssues);
        return;
      }
    }
  }

  delete data._uncheckedRules;
  var result = await apiRequest("POST", "/config/section", {
    section: sectionName,
    data: data,
  });

  if (result.code === 200) {
    showToast(
      result.message || "配置已保存。变更需重启服务才能完全生效。",
      "success",
    );
    loadConfig();
    loadHealth();
  } else {
    showToast(result.message || "保存失败", "error");
  }
}

async function validateBasicSection() {
  var data = _buildBasicData();
  var sourceDir = (data.source_dir || "").replace(/\/+$/, "");
  var tempDir = (data.temp_dir || "").replace(/\/+$/, "");
  var recycleDir = (
    (data.source_policy &&
      (data.source_policy.recycle_dir || data.source_policy.quarantine_dir)) ||
    ""
  ).replace(/\/+$/, "");

  var missing = [];
  if (!sourceDir) missing.push("源目录");
  if (!tempDir) missing.push("中转目录");
  if (!recycleDir) missing.push("回收站路径");
  if (missing.length > 0) {
    showToast(missing.join("、") + " 为必填项", "error");
    return;
  }

  var conflicts = [];
  if (sourceDir && tempDir && sourceDir === tempDir)
    conflicts.push("源目录与中转目录不能相同");
  if (sourceDir && recycleDir && sourceDir === recycleDir)
    conflicts.push("源目录与回收站目录不能相同");
  if (tempDir && recycleDir && tempDir === recycleDir)
    conflicts.push("中转目录与回收站目录不能相同");
  if (conflicts.length > 0) {
    showToast(conflicts.join("；"), "error");
    return;
  }

  showToast("正在检查路径权限...", "info");
  var permCheck = await apiRequest("POST", "/config/check-permission", {
    source_dir: data.source_dir,
    temp_dir: data.temp_dir,
    log_dir: currentConfig.log_dir || "",
    path_rules: currentConfig.path_rules || [],
  });
  if (permCheck && permCheck.code === 200 && permCheck.data) {
    if (!permCheck.data.all_ok) {
      showPermissionDialog(permCheck.data.issues || []);
    } else {
      showToast("路径权限验证通过！", "success");
    }
  } else {
    showToast("权限检查接口异常", "warning");
  }
}

async function testPathPermission(inputId, needWrite) {
  var input = document.getElementById(inputId);
  var resultEl = document.getElementById("perm-result-" + inputId);
  if (!input || !resultEl) return;

  var path = (input.value || "").trim();
  if (!path) {
    resultEl.className = "perm-result perm-error";
    resultEl.textContent = "请先填写路径再测试";
    return;
  }

  resultEl.className = "perm-result perm-loading";
  resultEl.textContent = "正在测试...";

  var result = await apiRequest("POST", "/path/test", {
    path: path,
    need_write: !!needWrite,
  });
  if (result && result.code === 200 && result.data) {
    var d = result.data;
    if (d.ok) {
      resultEl.className = "perm-result perm-ok";
      resultEl.innerHTML =
        "✅ " +
        (d.message || "权限正常") +
        (d.user ? "（当前用户: " + d.user + "）" : "");
    } else {
      resultEl.className = "perm-result perm-error";
      resultEl.innerHTML =
        "❌ " +
        (d.message || "权限测试失败") +
        (d.hint
          ? '<div style="margin-top:6px;white-space:pre-line;font-size:12px;">' +
            d.hint +
            "</div>"
          : "");
    }
  } else {
    resultEl.className = "perm-result perm-error";
    resultEl.textContent =
      "测试失败: " + ((result && result.message) || "未知错误");
  }
}

async function testAllImportPaths() {
  var resultEl = document.getElementById("perm-result-import-dirs");
  if (!resultEl) return;

  var path_rules = collectPathRulesFromDOM();
  if (!path_rules || path_rules.length === 0) {
    resultEl.className = "perm-result perm-error";
    resultEl.textContent = "请先添加入库规则";
    return;
  }

  resultEl.className = "perm-result perm-loading";
  resultEl.textContent = "正在测试所有入库目录...";

  var result = await apiRequest("POST", "/config/check-permission", {
    source_dir: "",
    temp_dir: "",
    log_dir: "",
    path_rules: path_rules,
  });

  if (result && result.code === 200 && result.data) {
    var issues = result.data.issues || [];
    if (issues.length === 0) {
      resultEl.className = "perm-result perm-ok";
      resultEl.textContent = "✅ 所有入库目录权限正常";
    } else {
      var html =
        '<div style="font-weight:600;margin-bottom:6px;">❌ 以下入库目录权限有问题：</div>';
      issues.forEach(function (it) {
        html += '<div style="margin-bottom:8px;">';
        html += '<div style="font-family:monospace;">' + it.path + "</div>";
        html +=
          '<div style="margin-top:4px;font-size:12px;">' +
          (it.message || "") +
          "</div>";
        if (it.hint) {
          html +=
            '<div style="margin-top:4px;padding:6px;background:#fffbeb;border-radius:4px;color:#92400e;font-size:12px;white-space:pre-line;">' +
            it.hint +
            "</div>";
        }
        html += "</div>";
      });
      resultEl.className = "perm-result perm-error";
      resultEl.innerHTML = html;
    }
  } else {
    resultEl.className = "perm-result perm-error";
    resultEl.textContent =
      "测试失败: " + ((result && result.message) || "未知错误");
  }
}

function parsePathRulesYaml(text) {
  var rules = [];
  var lines = text.split("\n");
  var current = null;
  var inConditions = false;
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var trimmed = line.replace(/\s+$/, "");
    if (!trimmed.trim()) continue;
    if (/^\s*-\s+/.test(trimmed)) {
      if (current) rules.push(current);
      current = { conditions: {}, template: "" };
      inConditions = false;
      var rest = trimmed.replace(/^\s*-\s+/, "");
      if (rest.indexOf("conditions:") === 0) inConditions = true;
      continue;
    }
    if (!current) continue;
    var kvMatch = trimmed.match(/^\s*([a-zA-Z_]+)\s*:\s*(.*)$/);
    if (kvMatch) {
      var key = kvMatch[1];
      var val = kvMatch[2].trim().replace(/^['"]|['"]$/g, "");
      if (key === "conditions") {
        inConditions = true;
        continue;
      }
      if (key === "template") {
        inConditions = false;
        current.template = val;
        continue;
      }
      if (inConditions) {
        current.conditions[key] = val;
      }
    }
  }
  if (current) rules.push(current);
  return rules;
}

function showPermissionDialog(issues) {
  var overlay = document.createElement("div");
  overlay.className = "perm-dialog-overlay";

  var html = '<div class="perm-dialog">';
  html += '<div class="perm-dialog-header">⚠️ 权限不足，无法保存配置</div>';
  html += '<div class="perm-dialog-body">';
  html +=
    '<div style="margin-bottom:12px;color:#475569;">检测到以下路径权限不足，请按指引完成授权后重新保存：</div>';
  issues.forEach(function (it) {
    html += '<div class="perm-issue-item">';
    html +=
      '<div class="perm-issue-field">字段: ' + (it.field || "-") + "</div>";
    html += '<div class="perm-issue-path">路径: ' + (it.path || "-") + "</div>";
    if (it.rule_template) {
      html +=
        '<div style="font-size:12px;color:#64748b;margin-top:2px;">所属规则模板: ' +
        it.rule_template +
        "</div>";
    }
    html +=
      '<div style="margin-top:6px;color:#991b1b;">' +
      (it.message || "") +
      "</div>";
    if (it.hint) {
      html += '<div class="perm-issue-hint">' + it.hint + "</div>";
    }
    html += "</div>";
  });
  html += "</div>";
  html += '<div class="perm-dialog-footer">';
  html +=
    '<button class="btn btn-primary" onclick="this.closest(\'.perm-dialog-overlay\').remove()">我知道了</button>';
  html += "</div>";
  html += "</div>";

  overlay.innerHTML = html;
  document.body.appendChild(overlay);
}

function toggleAdvancedSection(headerEl) {
  var section = headerEl.closest(".config-section");
  if (!section) return;
  var body = section.querySelector(".config-section-body");
  if (!body) return;
  var isHidden = body.classList.contains("collapsed-section");
  if (isHidden) {
    body.classList.remove("collapsed-section");
  } else {
    body.classList.add("collapsed-section");
  }
  headerEl.classList.toggle("expanded", isHidden);
}

function onHermesToggle() {
  var checkbox = document.getElementById("cfg-hermes_enabled");
  var hermesSection = document.getElementById("hermes-config-section");
  if (!checkbox || !hermesSection) return;
  var enabled = checkbox.checked;
  var formGroups = hermesSection.querySelectorAll(".form-group");
  for (var i = 1; i < formGroups.length; i++) {
    if (enabled) {
      formGroups[i].classList.remove("collapsed-section");
    } else {
      formGroups[i].classList.add("collapsed-section");
    }
  }
  var formRows = hermesSection.querySelectorAll(".form-row");
  formRows.forEach(function (row) {
    if (enabled) {
      row.classList.remove("collapsed-section");
    } else {
      row.classList.add("collapsed-section");
    }
  });
}

function onSourceCleanerToggle() {
  var checkbox = document.getElementById("cfg-source_cleaner-enabled");
  if (!checkbox) return;
  var enabled = checkbox.checked;
  var fields = document.getElementById("source-cleaner-fields");
  if (fields) {
    fields.style.display = enabled ? "" : "none";
  }
  var aiCheckbox = document.getElementById("cfg-source_cleaner-ai_enabled");
  var mergeGroup = document.getElementById(
    "source-cleaner-merge-strategy-group",
  );
  if (mergeGroup) {
    mergeGroup.style.display =
      enabled && aiCheckbox && aiCheckbox.checked ? "" : "none";
  }
  var aiPromptRow = document.getElementById("sc-ai-prompt-row");
  if (aiPromptRow) {
    aiPromptRow.style.display =
      enabled && aiCheckbox && aiCheckbox.checked ? "" : "none";
  }
}

