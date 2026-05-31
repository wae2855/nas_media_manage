import os

from media_importer.api import globals
from .utils import json_response


class PromptHandlersMixin:
    def _load_prompts_for_ui(self) -> dict:
        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            if config_path:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
            else:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            user_file = os.path.join(prompts_dir, "config", "scraper_prompts.md")
            example_file = os.path.join(prompts_dir, "config", "scraper_prompts.example.md")

            import yaml as _yaml

            sp = ""
            using_custom = False

            if os.path.isfile(user_file):
                with open(user_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if "system_prompt:" in content:
                    data = _yaml.safe_load(content)
                    if data and isinstance(data, dict):
                        sp = (data.get("system_prompt") or "").strip()
                        using_custom = bool(sp)

            if not sp and os.path.isfile(example_file):
                data = _yaml.safe_load(open(example_file, "r", encoding="utf-8").read())
                if data and isinstance(data, dict):
                    sp = (data.get("system_prompt") or "").strip()
                    using_custom = False

            if not sp:
                from media_importer.scraper.llm_scraper import LLMScraper
                ds = LLMScraper.DEFAULT_SYSTEM_PROMPT
                SEP = "【维度判断】\n当前需要判断的维度："
                if ds.endswith(SEP):
                    ds = ds[:-len(SEP)]
                return {"system_prompt": ds, "using_custom": False}

            return {"system_prompt": sp, "using_custom": using_custom}
        except Exception as e:
            import sys, traceback
            print(f"[ERROR] _load_prompts_for_ui failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return {"system_prompt": "", "using_custom": False}

    def _load_tmdb_prompts_for_ui(self) -> dict:
        try:
            from media_importer.scraper.llm_scraper import LLMScraper

            default_prompt = LLMScraper._get_default_provider_prompt('tmdb')

            config_path = globals._config.get("_config_path") if globals._config else None
            if config_path:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
            else:
                prompts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            user_file = os.path.join(prompts_dir, "config", "tmdb_prompts.md")

            import yaml as _yaml

            sp = ""
            using_custom = False

            if os.path.isfile(user_file):
                with open(user_file, "r", encoding="utf-8") as f:
                    content = f.read()
                if "system_prompt:" in content:
                    data = _yaml.safe_load(content)
                    if data and isinstance(data, dict):
                        sp = (data.get("system_prompt") or "").strip()
                        using_custom = bool(sp)

            if not sp:
                sp = default_prompt
                using_custom = False

            return {"system_prompt": sp, "using_custom": using_custom}
        except Exception as e:
            import sys, traceback
            print(f"[ERROR] _load_tmdb_prompts_for_ui failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return {"system_prompt": "", "using_custom": False}

    def _config_save_prompts(self, body: dict):
        try:
            if not body:
                json_response(self, 400, message="Empty body")
                return

            system_prompt = body.get("system_prompt", "").strip()

            config_path = globals._config.get("_config_path") if globals._config else None
            if config_path:
                prompts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(config_path))), "config", "scraper_prompts.md")
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                prompts_file = os.path.join(base_dir, "config", "scraper_prompts.md")

            head_comment = """# ============================================================
# LLM 刮削提示词配置 - 用户自定义
# ============================================================
# 在此文件中修改提示词内容，程序会优先使用此处配置
# 提示词分为两半：上半部（此文件）由您编写，下半部（维度列表+JSON Schema）由程序自动追加
# 如需恢复出厂默认，点击 WebUI 中的 "重置为默认" 即可

"""

            from ruamel.yaml import YAML
            from ruamel.yaml.scalarstring import LiteralScalarString

            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.width = 120

            doc = {}
            if system_prompt:
                doc["system_prompt"] = LiteralScalarString(system_prompt)

            with open(prompts_file, "w", encoding="utf-8") as f:
                f.write(head_comment)
                yaml.dump(doc, f)

            json_response(self, 200, message="提示词已保存，重启服务后生效")
        except Exception as e:
            json_response(self, 500, message="保存提示词失败: " + str(e))

    def _config_reset_prompts(self):
        try:
            config_path = globals._config.get("_config_path") if globals._config else None
            if config_path:
                prompts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(config_path))), "config", "scraper_prompts.md")
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                prompts_file = os.path.join(base_dir, "config", "scraper_prompts.md")

            if os.path.isfile(prompts_file):
                os.remove(prompts_file)

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
