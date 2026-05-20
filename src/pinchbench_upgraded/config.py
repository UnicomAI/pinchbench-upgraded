"""集中配置：常量、路径、规则文件查表。"""

from __future__ import annotations

import logging
import re
from pathlib import Path

# ── API ───────────────────────────────────────────────────────────────────────
BASE_URL = "https://api.pinchbench.com/api"
LEADERBOARD_LIMIT = 200
SUBMISSIONS_LIMIT = 100
FETCH_DELAY_MS = 500     # step1: 每次 submission 详情请求后等待

# ── 前端筛选默认值 ────────────────────────────────────────────────────────────
# min_obs 是 HTML 前端可视化筛选的初始阈值（运行次数 K 的最小展示阈值，默认 1）。
FILTER_DEFAULTS = {
    "min_obs": 1,
    "country": "all",
    "open_source": "all",
    "lang": "zh",
}

# ── 文件名安全化 ──────────────────────────────────────────────────────────────
_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|]')

def safe_filename(value: str) -> str:
    return _UNSAFE_CHARS.sub("_", value)


logger = logging.getLogger(__name__)


def load_overrides_category_zh(rules_path: Path) -> dict[str, str]:
    """从规则文件读取大类英文 → 中文翻译表。

    返回 ``{english_category_lower: chinese_name}``。规则文件不存在、字段缺失或为空时
    返回空 dict——分类是"渐进完善"而非"强制依赖"。
    """
    from pinchbench_upgraded.utils import read_json  # 延迟导入，避免循环依赖

    if not rules_path.exists():
        return {}
    raw = read_json(rules_path)
    if not isinstance(raw, dict):
        return {}
    table = raw.get("overrides_category_zh") or {}
    if not isinstance(table, dict):
        return {}
    return {
        str(k).strip().lower(): str(v).strip()
        for k, v in table.items()
        if str(k).strip() and str(v).strip()
    }


def load_overrides_task_zh(rules_path: Path) -> dict[str, str]:
    """从规则文件读取 task_id → 中文任务名覆盖表。

    返回 ``{task_id: chinese_name}``。缺失返回空 dict（HTML 显示时回退到 frontmatter.name 英文）。
    """
    from pinchbench_upgraded.utils import read_json

    if not rules_path.exists():
        return {}
    raw = read_json(rules_path)
    if not isinstance(raw, dict):
        return {}
    table = raw.get("overrides_task_zh") or {}
    if not isinstance(table, dict):
        return {}
    return {
        str(k).strip(): str(v).strip()
        for k, v in table.items()
        if str(k).strip() and str(v).strip()
    }
