#!/usr/bin/env python3
import os
import re
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from media_importer.core.config_view import ConfigView
from media_importer.core.safety import move_to_recycle, move_dir_to_recycle

logger = logging.getLogger(__name__)

AI_SYSTEM_PROMPT = """你是"影音库AI智能整理"系统的源目录清理助手。你的任务是分析源目录中的文件，判断哪些是垃圾文件应该删除，哪些是影视相关文件应该保留。

【分析原则】
1. 整体视角：分析整个目录的文件构成，而非孤立判断单个文件
2. 容量对比：同一目录下，视频文件大小差异显著时，小文件大概率是广告/样本/预告
3. 命名模式：文件名含 sample、trailer、预告、花絮、广告等关键词的应删除
4. 关联识别：与视频同名的 .nfo、.jpg、.png 等是影视元数据/海报，应保留
5. 字幕文件：.srt、.ass 等字幕文件应保留
6. 保守原则：无法确定时倾向于保留，避免误删

【判断标准】
- 主视频文件（通常最大的视频文件）→ 保留
- 字幕文件 → 保留
- 与主视频同名的元数据/海报 → 保留
- 样本/预告/广告视频（明显小于主视频）→ 删除
- BT下载附带的无用文件（.url, .txt说明, 下载站广告图）→ 删除
- 无法判断的文件 → 保留

【输出格式】
请严格按以下JSON格式返回，不要添加任何解释文字：
{
    "analysis": "简要分析说明",
    "decisions": {
        "文件名": {"action": "keep或delete", "reason": "判断理由"}
    }
}"""


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
        self.ai_prompt = cleaner.ai_prompt or AI_SYSTEM_PROMPT

        self.video_extensions = set(self.view.paths.video_extensions)
        self.subtitle_extensions = set(self.view.paths.subtitle_extensions)
        self.media_extensions = self.video_extensions | self.subtitle_extensions

    def preview(self, task_paths: set = None) -> list:
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
        merged.extend(self._scan_blacklist_dirs(task_paths))

        return merged

    def execute(self, task_paths: set = None,
                merge_strategy: str = None) -> dict:
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

    def ai_preview(self, task_paths: set = None) -> dict:
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

        for dirpath, dirnames, filenames in os.walk(self.source_dir):
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
        for dirpath, dirnames, filenames in os.walk(self.source_dir):
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

        for pattern in self.blacklist_patterns:
            if self._match_pattern(fname, fpath, pattern):
                return "blacklist_pattern", f"匹配黑名单: {pattern}"

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

        for dirpath, dirnames, filenames in os.walk(self.source_dir):
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
        llm_config = self.view.llm
        api_key = llm_config.api_key
        if not api_key:
            return {}

        api_base = llm_config.effective_fast_base_url
        model = llm_config.source_cleaner_model

        prompt = self._build_cleaner_prompt(dir_path, files)
        try:
            response_text = self._call_llm(api_base, api_key, model, prompt)
            return self._parse_ai_response(response_text)
        except Exception as e:
            logger.warning(f"AI 分析目录失败 {dir_path}: {e}")
            return {}

    def _build_cleaner_prompt(self, dir_path: str, files: list) -> str:
        files_desc = json.dumps(files, ensure_ascii=False, indent=2)
        return f"{self.ai_prompt}\n\n【待分析目录】\n目录: {dir_path}\n文件列表:\n{files_desc}"

    def _call_llm(self, api_base: str, api_key: str, model: str, prompt: str) -> str:
        url = f"{api_base.rstrip('/')}/chat/completions"
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": self.ai_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

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

    def _scan_blacklist_dirs(self, task_paths: set) -> list:
        items = []
        blacklist_dir_names = {"sample", "samples", "预告", "花絮", "trailer", "trailers", "extras"}

        for dirpath, dirnames, filenames in os.walk(self.source_dir, topdown=True):
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
                        total_size = 0
                        for dp, dn, fns in os.walk(full_dir):
                            for fn in fns:
                                try:
                                    total_size += os.path.getsize(os.path.join(dp, fn))
                                except OSError:
                                    pass
                        items.append({
                            "path": full_dir,
                            "size_mb": round(total_size / (1024 * 1024), 2),
                            "category": "blacklist_dir",
                            "reason": f"黑名单目录: {dname}",
                            "source": "rule",
                        })
                        matched_dirs.append(dname)

            for d in matched_dirs:
                dirnames.remove(d)

        return items

    def _find_empty_dirs(self) -> list:
        items = []
        for dirpath, dirnames, filenames in os.walk(self.source_dir, topdown=False):
            if dirpath == self.source_dir:
                continue
            if not os.listdir(dirpath):
                items.append({
                    "path": dirpath,
                    "size_mb": 0,
                    "category": "empty_dir",
                    "reason": "空目录",
                })
        return items
