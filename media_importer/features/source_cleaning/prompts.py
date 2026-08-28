"""源目录清理器内置 LLM 提示词（ADR-0010：随 AI 刮削移除，从 features/prompts 收敛而来）。
"""

SYSTEM_PROMPT = "你是影音库AI智能整理系统的源目录清理助手。判断源目录中哪些文件应清理、哪些应保留。"

INSTRUCTION = """【分析原则】
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
- 无法判断的文件 → 保留"""

OUTPUT_FORMAT = (
    "## 输出要求\n"
    "请严格按以下JSON格式返回，不要添加任何解释文字：\n"
    '{"analysis": "...", "decisions": {"文件名": {"action": "keep或delete", "reason": "判断理由"}}}'
)


def build_cleaner_prompt(dir_path: str, files: list) -> tuple:
    """组装清理器 (system_prompt, user_prompt)。"""
    import json

    files_desc = json.dumps(files, ensure_ascii=False, indent=2)
    data_context = f"【待分析目录】\n目录: {dir_path}\n文件列表:\n{files_desc}"
    user_prompt = "\n\n".join([INSTRUCTION, OUTPUT_FORMAT, data_context])
    return SYSTEM_PROMPT, user_prompt
