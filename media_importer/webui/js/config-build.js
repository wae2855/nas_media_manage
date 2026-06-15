// config-build.js - provider config UI and section builders
  return !value || value.indexOf("***") !== -1;
}

var _cachedProviderSchemas = {};

async function loadProviderConfigUI(metadata) {
  var container = document.getElementById("provider-configs-container");
  if (!container) return;
  container.innerHTML = "";
  var providerList = metadata.providers || [];
  var allProviders = [];
  try {
    var result = await apiRequest("GET", "/providers");
    if (result.code === 200 && result.data && result.data.providers) {
      allProviders = result.data.providers;
      _cachedProviderSchemas = {};
      for (var i = 0; i < allProviders.length; i++) {
        var p = allProviders[i];
        _cachedProviderSchemas[p.type] = p.config_schema || { fields: [] };
      }
      for (var i = 0; i < allProviders.length; i++) {
        var p = allProviders[i];
        var savedConfig = null;
        for (var j = 0; j < providerList.length; j++) {
          if (providerList[j].type === p.type) {
            savedConfig = providerList[j];
            break;
          }
        }
        var card = renderProviderCard(p, savedConfig);
        container.appendChild(card);
      }
    }
  } catch (e) {
    container.innerHTML =
      '<div class="provider-empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><div class="provider-empty-state-title">加载 Provider 配置失败</div><div class="provider-empty-state-desc">请检查服务是否正常运行后刷新页面</div></div>';
  }
  if (allProviders.length === 0) {
    container.innerHTML =
      '<div class="provider-empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg><div class="provider-empty-state-title">暂无可用的 Provider</div><div class="provider-empty-state-desc">请检查后端服务配置</div></div>';
  }
}

