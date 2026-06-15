var _apiKeyPending = false;

function getApiBase() {
  var path = window.location.pathname;
  var idx = path.indexOf("/index.cgi");
  if (idx >= 0) {
    return path.substring(0, idx + "/index.cgi".length);
  }
  return "";
}

function getApiKey() {
  return localStorage.getItem("nas_api_key") || "";
}

function setApiKey(key) {
  localStorage.setItem("nas_api_key", key);
}

function showApiKeyModal() {
  var input = document.getElementById("api-key-input");
  if (input) input.value = getApiKey();
  document.getElementById("api-key-modal").style.display = "";
  setTimeout(function () {
    if (input) {
      input.focus();
      input.onkeydown = function (e) {
        if (e.key === "Enter") submitApiKey();
      };
    }
  }, 100);
}

function submitApiKey() {
  var input = document.getElementById("api-key-input");
  var key = input ? input.value.trim() : "";
  if (key) {
    setApiKey(key);
    closeModal("api-key-modal");
    location.reload();
  } else {
    showToast("请输入 API Key", "error");
  }
}

function promptApiKey() {
  showApiKeyModal();
}

async function apiRequest(method, endpoint, body = null, options = {}) {
  try {
    const reqOptions = {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
    };

    const apiKey = getApiKey();
    if (apiKey) {
      reqOptions.headers["Authorization"] = "Bearer " + apiKey;
    }

    let url = getApiBase() + "/api" + endpoint;

    if (body) {
      if (method === "GET") {
        const params = new URLSearchParams();
        for (const [key, value] of Object.entries(body)) {
          if (value !== undefined && value !== null) {
            params.append(key, value);
          }
        }
        const qs = params.toString();
        if (qs) url += "?" + qs;
      } else {
        reqOptions.body = JSON.stringify(body);
      }
    }

    if (options.timeoutMs) {
      const controller = new AbortController();
      reqOptions.signal = controller.signal;
      const timeoutId = setTimeout(() => controller.abort(), options.timeoutMs);
      try {
        const response = await fetch(url, reqOptions);
        clearTimeout(timeoutId);
        return await _handleApiResponse(response);
      } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === "AbortError") {
          return { code: 408, status: "timeout", message: "请求超时" };
        }
        throw error;
      }
    }

    const response = await fetch(url, reqOptions);
    return await _handleApiResponse(response);
  } catch (error) {
    console.error("API request failed:", error);
    return { code: 500, status: "error", message: "网络请求失败" };
  }
}

async function _handleApiResponse(response) {
  if (response.status === 401) {
    if (!_apiKeyPending) {
      _apiKeyPending = true;
      showApiKeyModal();
    }
    return {
      code: 401,
      status: "unauthorized",
      message: "认证失败：请提供有效的 API Key",
    };
  }

  const data = await response.json();
  return data;
}

async function checkApiKeyRequired() {
  try {
    var resp = await fetch(getApiBase() + "/api/health");
    if (resp.status === 401) {
      document.getElementById("api-key-btn").style.display = "";
      if (!getApiKey()) {
        showApiKeyModal();
      }
    }
  } catch (e) {
    // ignore
  }
}
