import os
import re


def _extract_series_name(filename: str) -> str:
    name = os.path.splitext(filename)[0]
    name = re.sub(r'[._]', ' ', name)
    name = re.sub(r'\b[Ss]\d{1,2}[Ee]\d{1,2}\b.*$', '', name)
    name = re.sub(r'\b[Ss]\d{1,2}\b.*$', '', name)
    name = re.sub(r'\b(?:2160p|1080p|720p|480p|4K|UHD|HDR)\b.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(?:WEB|HDTV|BluRay|BDRip|WEBRip|WEB-DL|REMUX)\b.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b(?:x264|x265|HEVC|H\.?264|H\.?265|AAC|DTS|DD|ATMOS)\b.*$', '', name, flags=re.IGNORECASE)
    name = name.strip(' -.')
    return name


PIPELINE_STEPS = [
    (1, "scan", "扫描源目录"),
    (2, "copy", "复制到临时目录"),
    (3, "scrape", "AI刮削元数据"),
    (4, "validate", "验证刮削结果"),
    (5, "classify", "分类匹配路径"),
    (6, "dedup", "同名文件检测"),
    (7, "rename", "生成目标文件名"),
    (8, "import", "入库移动文件"),
    (9, "notify", "发送通知"),
    (10, "record", "记录处理结果"),
]


class PipelineError(Exception):
    pass


class PipelineSkipError(Exception):
    pass


class PipelineCancelled(Exception):
    """The user requested a cooperative stop before the library commit point."""

    pass


class PipelineReviewRequired(Exception):
    """流水线发现需要用户逐项处理的结构化冲突。"""

    def __init__(self, message: str, result: dict | None = None):
        super().__init__(message)
        self.result = result or {}
