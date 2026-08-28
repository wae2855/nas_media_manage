import json
import logging
import os
from datetime import datetime
from typing import Optional

from media_importer.features.configuration import ConfigView
from media_importer.features.recycle import move_dir_to_recycle, move_to_recycle
from media_importer.features.source_cleaning.prompts import SYSTEM_PROMPT, build_cleaner_prompt
from media_importer.infrastructure.llm import LLMClient

logger = logging.getLogger(__name__)
ai_logger = logging.getLogger("media_importer.ai")

__all__ = ["AI_SYSTEM_PROMPT", "SourceCleaner"]


AI_SYSTEM_PROMPT = SYSTEM_PROMPT


class SourceCleaner:
    def __init__(self, config: dict):
        self.full_config = config
        self.view = ConfigView.from_dict(config)
        self.config = config.get("source_cleaner", {})
        cleaner = self.view.source_cleaner
        self.source_dir = self.view.paths.source_dir
        self.recycle_dir = self.view.source_policy.recycle_dir
        self.cleanup_mode = cleaner.cleanup_mode
        self.ai_enabled = cleaner.ai_enabled
        self.merge_strategy = cleaner.merge_strategy
        self.junk_video_max_size_mb = cleaner.junk_video_max_size_mb
        self.delete_extensions = set(cleaner.delete_extensions)
        self.protect_extensions = set(cleaner.protect_extensions)
        self.blacklist_patterns = cleaner.blacklist_patterns
        self.cleanup_empty_dirs = cleaner.cleanup_empty_dirs

        self.llm = LLMClient(config)

        self.video_extensions = set(self.view.paths.video_extensions)
        self.subtitle_extensions = set(self.view.paths.subtitle_extensions)
        self.media_extensions = self.video_extensions | self.subtitle_extensions

    def preview(self, task_paths: Optional[set] = None) -> list:
        if not self.source_dir or not os.path.isdir(self.source_dir):
            return []
        task_paths = task_paths or set()

        rule_items = self._rule_classify_all(task_paths)
        ai_items = {}
        if self.ai_enabled:
            ai_items = self._ai_analyze_all(task_paths)

        merged = self._merge_results(rule_items, ai_items)

        if self.cleanup_empty_dirs:
            merged.extend(self._find_empty_dirs())
        merged.extend(self._scan_blacklist_dirs(task_paths, rule_items))

        return merged

    def execute(self, task_paths: Optional[set] = None,
                merge_strategy: Optional[str] = None) -> dict:
        if merge_strategy:
            self.merge_strategy = merge_strategy

        items = self.preview(task_paths)
        moved_items = []
        rule_only_count = 0
        ai_only_count = 0
        both_count = 0

        for item in items:
            if item.get("category") == "empty_dir":
                ok, dest_path, _ = move_dir_to_recycle(
                    item["path"], self.recycle_dir,
                    reason="source_cleaner:empty_dir",
                    source_dir=self.source_dir,
                )
                if ok:
                    item["recycle_path"] = dest_path
                    moved_items.append(item)
                continue

            if item.get("category") == "blacklist_dir":
                ok, dest_path, _ = move_dir_to_recycle(
                    item["path"], self.recycle_dir,
                    reason="source_cleaner:blacklist_dir",
                    source_dir=self.source_dir,
                )
                if ok:
                    item["recycle_path"] = dest_path
                    moved_items.append(item)
                continue

            ok, dest_path, _ = move_to_recycle(
                item["path"], self.recycle_dir,
                reason=f"source_cleaner:{item['category']}",
                source_dir=self.source_dir,
            )
            if ok:
                item["recycle_path"] = dest_path
                moved_items.append(item)
                source = item.get("source", "")
                if source == "rule":
                    rule_only_count += 1
                elif source == "ai":
                    ai_only_count += 1
                elif source == "both":
                    both_count += 1

        record = {
            "executed_at": datetime.now().isoformat(),
            "mode": self.cleanup_mode,
            "merge_strategy": self.merge_strategy,
            "total_files": len(moved_items),
            "total_size_mb": round(sum(i.get("size_mb", 0) for i in moved_items), 2),
            "rule_only_count": rule_only_count,
            "ai_only_count": ai_only_count,
            "both_count": both_count,
            "items": moved_items,
        }
        logger.info(f"源目录清理完成: 清理 {len(moved_items)} 个文件, {record['total_size_mb']}MB")
        return record

    def ai_preview(self, task_paths: Optional[set] = None) -> dict:
        if not self.ai_enabled:
            return {"status": "disabled", "items": []}
        if not self.source_dir or not os.path.isdir(self.source_dir):
            return {"status": "error", "message": "源目录不存在"}

        task_paths = task_paths or set()
        ai_items = self._ai_analyze_all(task_paths)
        items = []
        for fpath, info in ai_items.items():
            if info.get("action") == "delete":
                size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 2) if os.path.isfile(fpath) else 0
                items.append({
                    "path": fpath,
                    "size_mb": size_mb,
                    "category": "ai_delete",
                    "reason": info.get("reason", "AI判定删除"),
                    "source": "ai",
                })
        return {"status": "ok", "directories_analyzed": getattr(self, "_ai_dirs_analyzed", 0), "items": items}

    def _rule_classify_all(self, task_paths: set) -> dict:
        results = {}
        video_stems_in_dirs = self._collect_video_stems()

        for dirpath, _dirnames, filenames in os.walk(self.source_dir):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if fpath in task_paths:
                    continue
                category, reason = self._classify_file(fpath, video_stems_in_dirs.get(dirpath, []))
                if category:
                    size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 2) if os.path.isfile(fpath) else 0
                    results[fpath] = {
                        "path": fpath,
                        "size_mb": size_mb,
                        "category": category,
                        "reason": reason,
                        "source": "rule",
                    }
        return results

    def _collect_video_stems(self) -> dict:
        stems = {}
        for dirpath, _dirnames, filenames in os.walk(self.source_dir):
            dir_stems = []
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.video_extensions:
                    dir_stems.append(os.path.splitext(fname)[0])
            stems[dirpath] = dir_stems
        return stems

    def _classify_file(self, fpath: str, video_stems: list) -> tuple:
        fname = os.path.basename(fpath)
        ext = os.path.splitext(fname)[1].lower()

        if ext in self.protect_extensions:
            return "", ""

        if ext in self.video_extensions:
            if self.junk_video_max_size_mb > 0 and os.path.isfile(fpath):
                size_mb = os.path.getsize(fpath) / (1024 * 1024)
                if size_mb < self.junk_video_max_size_mb:
                    return "junk_video", f"视频文件 {size_mb:.1f}MB < 阈值 {self.junk_video_max_size_mb}MB"
            return "", ""

        if ext in self.subtitle_extensions:
            return "", ""

        for pattern in self.blacklist_patterns:
            if self._match_pattern(fname, fpath, pattern):
                return "blacklist_pattern", f"匹配黑名单: {pattern}"

        if ext in self.delete_extensions:
            return "delete_extension", f"后缀名在删除列表: {ext}"

        if self.cleanup_mode == "media_only":
            return "non_media", f"非媒体文件(media_only模式): {ext}"

        if self.cleanup_mode == "media_and_related":
            if self._is_companion_file(fname, ext, video_stems):
                return "", ""
            return "non_media", f"非影视相关文件(media_and_related模式): {ext}"

        return "", ""

    def _is_companion_file(self, fname: str, ext: str, video_stems: list) -> bool:
        if ext in self.media_extensions:
            return True
        file_stem = os.path.splitext(fname)[0]
        for vstem in video_stems:
            if file_stem == vstem:
                return True
            if file_stem.startswith(vstem + "-") or file_stem.startswith(vstem + "."):
                return True
            if file_stem.startswith(vstem + "_") or file_stem.startswith(vstem + " "):
                return True
        return False

    def _match_pattern(self, fname: str, fpath: str, pattern: str) -> bool:
        if "*" in pattern or "?" in pattern:
            import fnmatch
            return fnmatch.fnmatch(fname, pattern) or fnmatch.fnmatch(fpath, pattern)
        return pattern.lower() in fname.lower() or pattern.lower() in fpath.lower()

    def _merge_results(self, rule_items: dict, ai_items: dict) -> list:
        merged = {}
        for fpath, info in rule_items.items():
            merged[fpath] = dict(info)

        for fpath, ai_info in ai_items.items():
            ai_action = ai_info.get("action", "keep")
            if fpath in merged:
                if ai_action == "delete":
                    merged[fpath]["source"] = "both"
                    merged[fpath]["reason"] += f" + AI: {ai_info.get('reason', '')}"
                else:
                    if self.merge_strategy == "union":
                        pass
                    else:
                        del merged[fpath]
            else:
                if ai_action == "delete":
                    if self.merge_strategy == "union":
                        size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 2) if os.path.isfile(fpath) else 0
                        merged[fpath] = {
                            "path": fpath,
                            "size_mb": size_mb,
                            "category": "ai_delete",
                            "reason": f"AI判定: {ai_info.get('reason', '')}",
                            "source": "ai",
                        }

        return list(merged.values())

    def _ai_analyze_all(self, task_paths: set) -> dict:
        results = {}
        dirs_analyzed = 0

        for dirpath, _dirnames, filenames in os.walk(self.source_dir):
            dir_files = []
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if fpath in task_paths:
                    continue
                try:
                    size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 2) if os.path.isfile(fpath) else 0
                except OSError:
                    size_mb = 0
                ext = os.path.splitext(fname)[1].lower()
                dir_files.append({"name": fname, "size_mb": size_mb, "ext": ext})

            if not dir_files:
                continue

            ai_decisions = self._ai_analyze_directory(dirpath, dir_files)
            dirs_analyzed += 1

            if ai_decisions:
                for fname, decision in ai_decisions.items():
                    fpath = os.path.join(dirpath, fname)
                    if os.path.exists(fpath):
                        results[fpath] = decision

        self._ai_dirs_analyzed = dirs_analyzed
        return results

    def _ai_analyze_directory(self, dir_path: str, files: list) -> dict:
        if not self.llm.enabled:
            return {}

        ai_logger.info(
            f"ai.scene.business scene=source_clean trigger=manual "
            f"dir={dir_path!r} file_count={len(files)}"
        )
        system_prompt, user_prompt = build_cleaner_prompt(dir_path, files)
        try:
            response_text = self.llm.call(system_prompt, user_prompt)
            return self._parse_ai_response(response_text)
        except Exception as e:
            logger.warning(f"AI 分析目录失败 {dir_path}: {e}")
            return {}

    def _parse_ai_response(self, response_text: str) -> dict:
        try:
            text = response_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1])
            parsed = json.loads(text)
            decisions = parsed.get("decisions", {})
            result = {}
            for fname, dec in decisions.items():
                action = dec.get("action", "keep").lower()
                reason = dec.get("reason", "")
                result[fname] = {"action": action, "reason": reason}
            return result
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"AI 响应解析失败: {e}")
            return {}

    def _scan_blacklist_dirs(self, task_paths: set, rule_items: Optional[dict] = None) -> list:
        items = []
        blacklist_dir_names = {"sample", "samples", "预告", "花絮", "trailer", "trailers", "extras"}
        already_marked = set(rule_items.keys()) if rule_items else set()

        for dirpath, dirnames, _filenames in os.walk(self.source_dir, topdown=True):
            matched_dirs = []
            for dname in dirnames:
                dname_lower = dname.lower()
                is_blacklist = False

                for pattern in self.blacklist_patterns:
                    if self._match_pattern(dname, os.path.join(dirpath, dname), pattern):
                        is_blacklist = True
                        break

                if not is_blacklist and dname_lower in blacklist_dir_names:
                    is_blacklist = True

                if is_blacklist:
                    full_dir = os.path.join(dirpath, dname)
                    if full_dir not in task_paths:
                        video_stems = self._collect_video_stems().get(full_dir, [])
                        for dp, _dn, fns in os.walk(full_dir):
                            for fn in fns:
                                fpath = os.path.join(dp, fn)
                                if fpath in task_paths:
                                    continue
                                if fpath in already_marked:
                                    continue
                                category, reason = self._classify_file(fpath, video_stems)
                                if not category:
                                    continue
                                try:
                                    size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 2)
                                except OSError:
                                    size_mb = 0
                                items.append({
                                    "path": fpath,
                                    "size_mb": size_mb,
                                    "category": category,
                                    "reason": f"{reason}（位于黑名单目录 {dname}）",
                                    "source": "rule",
                                })
                        matched_dirs.append(dname)

            for d in matched_dirs:
                dirnames.remove(d)

        return items

    def _find_empty_dirs(self) -> list:
        items = []
        for dirpath, _dirnames, _filenames in os.walk(self.source_dir, topdown=False):
            if dirpath == self.source_dir:
                continue
            if not os.listdir(dirpath):
                items.append({
                    "path": dirpath,
                    "size_mb": 0,
                    "category": "empty_dir",
                    "reason": "空目录",
                    "source": "rule",
                })
        return items
