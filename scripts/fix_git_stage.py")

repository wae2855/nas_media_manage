import os
os.chdir('/Users/wangwei/Documents/code/nas_media_manage')
import subprocess

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr

# Reset all
run("git reset --mixed HEAD")

# Remove any remaining stages
print("=== Remove any staged changes")
run("git reset --mixed")
print(run("git status --porcelain"))
")

# Manually delete deleted files first
print("\n=== Staging deletions")
deleted = [
    "_deprecated",
    "config/tmdb_prompts.md",
    "media_importer/api_server.py",
    "media_importer/classifier.py",
    "media_importer/cloud_refresher.py",
    "media_importer/config_loader.py",
    "media_importer/config_validator.py",
    "media_importer/db.py",
    "media_importer/dimension_manager.py",
    "media_importer/file_analyzer.py",
    "media_importer/file_copier.py",
    "media_importer/file_mover.py",
    "media_importer/file_scanner.py",
    "media_importer/file_watcher.py",
    "media_importer/hermes_hook.py",
    "media_importer/hooks.py",
    "media_importer/llm_scraper.py",
    "media_importer/logger.py",
    "media_importer/metadata_scraper.py",
    "media_importer/metrics.py",
    "media_importer/permission_checker.py",
    "media_importer/pipeline.py",
    "media_importer/safety.py",
    "media_importer/task_manager.py",
    "media_importer/tmdb_client.py",
    "media_importer/webui/config.js",
    "restart_for_test.sh",
    "deploy/nas-media-importer/app/server/media_importer/api_server.py",
    "deploy/nas-media-importer/app/server/media_importer/classifier.py",
    "deploy/nas-media-importer/app/server/media_importer/cloud_refresher.py",
    "deploy/nas-media-importer/app/server/media_importer/config.js",
    "deploy/nas-media-importer/app/server/media_importer/config_loader.py",
    "deploy/nas-media-importer/app/server/media_importer/config_validator.py",
    "deploy/nas-media-importer/app/server/media_importer/db.py",
    "deploy/nas-media-importer/app/server/media_importer/dimension_manager.py",
    "deploy/nas-media-importer/app/server/media_importer/file_analyzer.py",
    "deploy/nas-media-importer/app/server/media_importer/file_copier.py",
    "deploy/nas-media-importer/app/server/media_importer/file_mover.py",
    "deploy/nas-media-importer/app/server/media_importer/file_scanner.py",
    "deploy/nas-media-importer/app/server/media_importer/file_watcher.py",
    "deploy/nas-media-importer/app/server/media_importer/hermes_hook.py",
    "deploy/nas-media-importer/app/server/media_importer/hooks.py",
    "deploy/nas-media-importer/app/server/media_importer/llm_scraper.py",
    "deploy/nas-media-importer/app/server/media_importer/logger.py",
    "deploy/nas-media-importer/app/server/media_importer/metadata_scraper.py",
    "deploy/nas-media-importer/app/server/media_importer/metrics.py",
    "deploy/nas-media-importer/app/server/media_importer/permission_checker.py",
    "deploy/nas-media-importer/app/server/media_importer/pipeline.py",
    "deploy/nas-media-importer/app/server/media_importer/safety.py",
    "deploy/nas-media-importer/app/server/media_importer/task_manager.py",
    "deploy/nas-media-importer/app/server/media_importer/tmdb_client.py",
    "deploy/nas-media-importer/app/server/media_importer/webui/config.js",
    "deploy/nas-media-importer/app/server/tests/test_dimensions.py",
    "deploy/nas-media-importer/app/server/tests/test_full_flow.py",
    "deploy/nas-media-importer/app/server/tests/test_sqlite_refactor.py",
    "deploy/nas-media-importer/app/server/tests/test_task_operations.py",
    "docs/01-requirements.md",
    "docs/02-design.md",
    "docs/03-development-plan.md",
    "docs/05-checklist.md",
    "docs/06-test-guide.md",
    "docs/07-hermes-integration-guide.md",
    "docs/README.md",
    "docs/SECURITY_AUDIT_REPORT.md",
    "docs/brainstorm-dimension-system.md",
    "docs/brainstorm-metadata-api-integration.md",
    "docs/fnos-deploy-guide.md",
    "docs/implementation-plan-metadata-api.md",
    "docs/status-simplification-plan.md",
    "docs/test-plan-dimension-system.md",
]
]

for d in deleted:
    if os.path.exists(d):
        pass
    else:
        run("git add -u \"%s" % d)

print(run("git status --porcelain"))
print("\n=== Add new files and modified:")
run("git add config.yaml.example")
run("git add config/scraper_prompts.example.md")
run("git add deploy/build_fpk.sh")
run("git add deploy/nas-media-importer/app/server/config.yaml.example")
run("git add deploy/nas-media-importer/app/server/config/config.yaml")
run("git add deploy/nas-media-importer/app/server/config/scraper_prompts.example.md")
run("git add deploy/nas-media-importer/app/server/config/tmdb_prompts.md")
run("git add deploy/nas-media-importer/app/server/media_importer/media_importer.py")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/css/base.css")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/css/config.css")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/css/dimensions.css")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/css/layout.css")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/css/tasks.css")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/index.html")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/js/config.js")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/js/dimensions.js")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/js/prompts.js")
run("git add deploy/nas-media-importer/app/server/media_importer/webui/js/tasks.js")
run("git add deploy/nas-media-importer/config.yaml.example")
run("git add media_importer/media_importer.py")
run("git add media_importer/webui/css/base.css")
run("git add media_importer/webui/css/components.css")
run("git add media_importer/webui/css/config.css")
run("git add media_importer/webui/css/dimensions.css")
run("git add media_importer/webui/css/layout.css")
run("git add media_importer/webui/css/tasks.css")
run("git add media_importer/webui/index.html")
run("git add media_importer/webui/js/app.js")
run("git add media_importer/webui/js/config.js")
run("git add media_importer/webui/js/dimensions.js")
run("git add media_importer/webui/js/path-rules.js")
run("git add media_importer/webui/js/prompts.js")
run("git add media_importer/webui/js/tasks.js")
run("git add start.sh")
run("git add tests/test_config_consumers.py")
run("git add tests/test_sqlite_refactor.py")
run("git add AGENTS.md")
run("git add README.md")
run("git add .gitignore")
# Add all untracked directories recursively (new directories without rename problem, but only directories recursively without fixtures:
print("\n=== Add new untracked")
subprocess.run("git add deploy/nas-media-importer/app/server/media_importer/ media_importer/ docs/ scripts/ tests/", shell=True)
subprocess.run("git reset --mixed")

# The __init__.py rename again to correct the wrong rename")
subprocess.run("git reset --mixed HEAD media_importer/__init__.py deploy/nas-media-importer/app/server/media_importer/__init__.py", shell=True)
subprocess.run("git add media_importer/__init__.py deploy/nas-media-importer/app/server/media_importer/__init__.py", shell=True)
subprocess.run("git add -u")

print("\n=== Final Status")
print(run("git status"))

=== Final git status:
status
