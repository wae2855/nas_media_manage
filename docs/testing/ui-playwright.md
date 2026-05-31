# UI Playwright Tests

UI tests require:

- Python `playwright` module.
- Browser binaries installed.
- Local service running on port 9855 unless a test overrides it.

Command reference:

```bash
pytest tests/test_frontend_*.py
pytest tests/test_scrape_ui.py
```
