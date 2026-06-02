# UI Playwright Tests

## Requirements

- Python `playwright` module.
- Browser binaries installed.
- Local service running on port 9855 for tests that use `BASE_URL = "http://localhost:9855"` or `http://127.0.0.1:9855`.

Install browser binaries when the local environment does not have them:

```bash
python3 -m playwright install chromium
```

## Service Modes

| Test group | Service dependency | Notes |
|------------|--------------------|-------|
| `tests/test_confidence_ui.py` | external service on `localhost:9855` | Does not start the backend. |
| `tests/test_confidence_v2_ui.py` | external service on `localhost:9855` | Does not start the backend. |
| `tests/test_confidence_config_ui.py` | external service on `localhost:9855` | Does not start the backend. |
| `tests/test_config_page_full.py` | external service on `localhost:9855` | Long UI suite; requires stable config data. |
| `tests/test_scrape_ui.py` | external service on `localhost:9855` | Uses live API/UI assumptions. |
| `tests/test_tmdb_config.py` | external service on `127.0.0.1:9855` | Script-style Playwright test. |
| `tests/test_frontend_recycle.py` | self-started test server | Starts `media_importer.api.handler.start_server` on an ephemeral port. |

## Start External Service

```bash
PYTHONPATH="${PWD}" python3 -m media_importer.media_importer -c config/config.yaml serve -p 9855 --host 127.0.0.1
```

Use this only when `config/config.yaml` is valid for the local machine. UI tests may read or write configuration through the API.

## Command Reference

```bash
pytest tests/test_frontend_recycle.py
pytest tests/test_confidence_ui.py tests/test_confidence_v2_ui.py tests/test_confidence_config_ui.py
pytest tests/test_config_page_full.py
pytest tests/test_scrape_ui.py
pytest tests/test_tmdb_config.py
```

## Regression Rule

- For backend/domain refactors, prefer non-UI tests first.
- For UI or API contract changes, run `tests/test_frontend_recycle.py` if recycle UI is affected.
- Run external-service UI suites only after starting the service and confirming port 9855 is free.
- If Playwright/browser binaries are missing, record that as environment blocked rather than a product regression.
