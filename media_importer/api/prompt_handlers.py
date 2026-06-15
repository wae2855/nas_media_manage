import os

from media_importer.features.prompts import PromptDefaults
from .utils import json_response


class PromptHandlersMixin:
    def _prompt_defaults(self, *, body: dict, params: dict, query: dict):
        json_response(self, 200, data=PromptDefaults.get_all())

    def _skill(self, *, body: dict, params: dict, query: dict):
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

    def _skills_list(self, *, body: dict, params: dict, query: dict):
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
