"""共享工具函数：JSON 读写与排行榜排序。"""

from __future__ import annotations

import json
from pathlib import Path


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def read_json_list(path: Path) -> list:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
        return data if isinstance(data, list) else [data]


def write_json(path: Path, data: object) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sort_ranking_rows(rows: list[dict]) -> list[dict]:
    """按成功率降序、性价比降序、耗时升序、供应商、模型名稳定排序。

    耗时字段兼容两种命名：
    - task row：`avg_duration_s`（单位秒）
    - category row：`avg_duration_min`（单位分钟）
    """
    def sort_key(r: dict):
        success = r["average_success_rate_pct"]
        value = r["value_score"]
        # 同一表内字段名一致，排序语义不受单位影响（不混合 task/category）
        duration = r.get("avg_duration_s")
        if duration is None:
            duration = r.get("avg_duration_min")
        return (
            -(success if success is not None else float("-inf")),
            -(value if value is not None else float("-inf")),
            (duration if duration is not None else float("inf")),
            r["provider"],
            r["model"],
        )
    return sorted(rows, key=sort_key)
