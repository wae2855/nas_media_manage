import os

from media_importer.api import globals
from media_importer.features.prompts import (
    load_global_prompt_for_ui,
    reset_global_prompt,
    save_global_prompt,
)
from .utils import json_response


class PromptHandlersMixin:
    def _load_prompts_for_ui(self) -> dict:
        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            return load_global_prompt_for_ui(config_path)
        except Exception as e:
            import sys, traceback
            print(f"[ERROR] _load_prompts_for_ui failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return {"system_prompt": "", "using_custom": False}

    def _load_tmdb_prompts_for_ui(self) -> dict:
        return self._provider_prompts_get("tmdb")

    def _config_save_prompts(self, body: dict):
        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            save_global_prompt(config_path, body)
            json_response(self, 200, message="提示词已保存，重启服务后生效")
        except ValueError as e:
            json_response(self, 400, message=str(e))
        except Exception as e:
            json_response(self, 500, message="保存提示词失败: " + str(e))

    def _config_reset_prompts(self):
        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            reset_global_prompt(config_path)
            json_response(self, 200, message="已恢复出厂默认提示词，重启服务后生效")
        except Exception as e:
            json_response(self, 500, message="恢复默认提示词失败: " + str(e))

    def _config_save_tmdb_prompts(self, body: dict):
        self._provider_prompts_save(body, 'tmdb')

    def _config_reset_tmdb_prompts(self):
        self._provider_prompts_reset({}, 'tmdb')

    def _skill(self):
        skill_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "hermes", "skills", "nas-ops", "nas-media-importer", "SKILL.md"
        )
        skill_path = os.path.normpath(skill_path)
        if not os.path.isfile(skill_path):
            json_response(self, 404, message="SKILL.md not found")
            return
        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            json_response(self, 500, message=f"Failed to read SKILL.md: {e}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        body_bytes = content.encode("utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body_bytes)
        self.wfile.flush()

    def _skills_list(self):
        skills_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "hermes", "skills"
        )
        skills_dir = os.path.normpath(skills_dir)
        skills = []
        if os.path.isdir(skills_dir):
            for root, dirs, files in os.walk(skills_dir):
                for f in files:
                    if f == "SKILL.md":
                        rel = os.path.relpath(root, skills_dir)
                        skill_file = os.path.join(root, f)
                        try:
                            with open(skill_file, "r", encoding="utf-8") as fh:
                                header = fh.read(512)
                            name = ""
                            for line in header.split("\n"):
                                if line.startswith("name:"):
                                    name = line.split(":", 1)[1].strip()
                                    break
                            skills.append({"path": rel, "name": name or rel})
                        except Exception:
                            skills.append({"path": rel, "name": rel})
        json_response(self, 200, data={"skills": skills, "total": len(skills)})
