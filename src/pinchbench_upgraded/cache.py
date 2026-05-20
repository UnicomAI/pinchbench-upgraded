"""只读访问 step1 的 submission 缓存。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pinchbench_upgraded.config import safe_filename
from pinchbench_upgraded.utils import read_json

logger = logging.getLogger(__name__)


class SubmissionCache:
    """单源只读访问 step1 的 submission detail / list 缓存。

    detail 缓存：``submissions/current/<provider>__<model>__<id>.json``
    list 缓存：  ``submissions/current_lists/<provider>__<model>.json``

    缺失时返回 ``None``——调用方决定如何处理（一般是 raise 提示重跑 fetch）。
    """

    def __init__(self, data_dir: Path) -> None:
        self._step1_detail_dir = data_dir / "submissions" / "current"
        self._step1_list_dir = data_dir / "submissions" / "current_lists"
        # 预构建 step1 submissions 索引：submission_id -> file_path
        self._step1_index: dict[str, Path] = {}
        if self._step1_detail_dir.exists():
            for p in self._step1_detail_dir.glob("*.json"):
                # 文件名格式：provider__model__submission_id.json
                parts = p.stem.rsplit("__", 1)
                if len(parts) == 2:
                    self._step1_index[parts[1]] = p

    def get_submission_detail(self, submission_id: str) -> Optional[dict]:
        path = self._step1_index.get(submission_id)
        if path is not None and path.exists():
            return read_json(path)
        return None

    def get_submission_list(self, model: str, provider: str) -> Optional[dict]:
        path = self._step1_list_dir / _list_cache_filename(model, provider)
        if path.exists():
            return read_json(path)
        return None


def _list_cache_filename(model: str, provider: str) -> str:
    safe_p = safe_filename(provider if provider else "unknown_provider")
    safe_m = safe_filename(model)
    return f"{safe_p}__{safe_m}.json"
