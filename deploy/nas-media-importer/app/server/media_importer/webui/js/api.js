var _apiKeyPending = false;

function getApiBase() {
    var path = window.location.pathname;
    var idx = path.indexOf('/index.cgi');
    if (idx >= 0) {
        return path.substring(0, idx + '/index.cgi'.length);
    }
    return '';
}

function getApiKey() {
    return localStorage.getItem('nas_api_key') || '';
}

function setApiKey(key) {
    localStorage.setItem('nas_api_key', key);
}

function showApiKeyModal() {
    var input = document.getElementById('api-key-input');
    if (input) input.value = getApiKey();
    document.getElementById('api-key-modal').style.display = '';
    setTimeout(function() {
        if (input) {
            input.focus();
            input.onkeydown = function(e) {
                if (e.key === 'Enter') submitApiKey();
            };
        }
    }, 100);
}

function submitApiKey() {
    var input = document.getElementById('api-key-input');
    var key = input ? input.value.trim() : '';
    if (key) {
        setApiKey(key);
        closeModal('api-key-modal');
        location.reload();
    } else {
        showToast('请输入 API Key', 'error');
    }
}

function promptApiKey() {
    showApiKeyModal();
}

async function apiRequest(method, endpoint, body = null) {
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };

        const apiKey = getApiKey();
        if (apiKey) {
            options.headers['Authorization'] = 'Bearer ' + apiKey;
        }

        if (body) {
            options.body = JSON.stringify(body);
        }

        const response = await fetch(getApiBase() + '/api' + endpoint, options);

        if (response.status === 401) {
            if (!_apiKeyPending) {
                _apiKeyPending = true;
                showApiKeyModal();
            }
            return { code: 401, status: 'unauthorized', message: '认证失败：请提供有效的 API Key' };
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('API request failed:', error);
        return { code: 500, status: 'error', message: '网络请求失败' };
    }
}

async function checkApiKeyRequired() {
    try {
        var resp = await fetch(getApiBase() + '/api/health');
        if (resp.status === 401) {
            document.getElementById('api-key-btn').style.display = '';
            if (!getApiKey()) {
                showApiKeyModal();
            }
        }
    } catch (e) {
        // ignore
    }
}
