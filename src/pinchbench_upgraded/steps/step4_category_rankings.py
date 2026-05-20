"""Step 4: 大类排行榜（按上游 task.category 自动分组，11 大类自动得出）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from pinchbench_upgraded.config import (
    FILTER_DEFAULTS,
    load_overrides_category_zh,
)
from pinchbench_upgraded.html.renderer import render_category_rankings
from pinchbench_upgraded.utils import read_json, write_json, sort_ranking_rows

logger = logging.getLogger(__name__)


def _aggregate_category_rows(
    task_ids_in_cat: list[str],
    ranking_models: list[dict],
    task_row_index: dict[tuple[str, str, str], dict],
) -> list[dict]:
    """对一组 task_ids 做大类聚合（公式）。

    每个模型的 K 跨 task 相同；任务级 cost 跨 task 也相同（= submission_cost_sum / K / N）。
    大类聚合公式：
      - run_count       = K（直接取任意 task row 的 run_count）
      - success_rate    = avg(各 task 的 success_rate)
      - cost            = 任务级 cost × T（T = 该大类内的 task 数）
      - duration        = sum(各 task 的 duration)         # 与 cost = task_cost × T 对称
      - value_score     = 大类 success_rate / 大类 cost
      - time_efficiency = 大类 success_rate / 大类 duration
    """
    rows: list[dict] = []
    T = len(task_ids_in_cat)

    for model in ranking_models:
        model_name = model["model"]
        model_provider = model["provider"]
        cat_task_rows: list[dict] = []

        for tid in task_ids_in_cat:
            row = task_row_index.get((tid, model_provider, model_name))
            if row is not None:
                cat_task_rows.append(row)

        if not cat_task_rows:
            continue

        # K 跨 task 相同，取首行即可
        run_count = int(cat_task_rows[0].get("run_count") or 0)

        success_vals: list[float] = []
        duration_vals: list[float] = []
        # 任务级 cost 跨 task 相同；这里取一个有值的即可，无需平均
        task_level_cost: float | None = None

        for r in cat_task_rows:
            if r.get("average_success_rate_pct") is not None:
                success_vals.append(float(r["average_success_rate_pct"]))
            if r.get("avg_duration_s") is not None:
                duration_vals.append(float(r["avg_duration_s"]))
            if task_level_cost is None and r.get("cost_per_run_usd") is not None:
                task_level_cost = float(r["cost_per_run_usd"])

        avg_success = round(sum(success_vals) / len(success_vals), 2) if success_vals else None
        # 大类耗时单位为分钟：sum(task 秒) / 60 → min；与 HTML 展示单位一致，无需前端 *60 / 60 换算
        avg_duration_min = round(sum(duration_vals) / 60, 2) if duration_vals else None
        cat_cost = round(task_level_cost * T, 4) if task_level_cost is not None else None
        value_score = (
            round(avg_success / cat_cost, 2)
            if avg_success is not None and cat_cost and cat_cost > 0
            else None
        )
        time_efficiency = (
            round(avg_success / avg_duration_min, 2)
            if avg_success is not None and avg_duration_min and avg_duration_min > 0
            else None
        )

        rows.append({
            "rank": None,
            "model": model_name,
            "provider": model_provider,
            "model_size_raw": model.get("model_size_raw"),
            "model_size_b": model.get("model_size_b"),
            "average_success_rate_pct": avg_success,
            "run_count": run_count,
            "cost_per_run_usd": cat_cost,
            "avg_duration_min": avg_duration_min,
            "value_score": value_score,
            "time_efficiency": time_efficiency,
        })

    sorted_rows = sort_ranking_rows(rows)
    for rank_i, r in enumerate(sorted_rows):
        r["rank"] = rank_i + 1
    return sorted_rows


def run(data_dir: Path, rules_path: Path) -> None:
    analysis_dir = data_dir / "analysis"
    task_ranking_dir = analysis_dir / "current_task_rankings"
    category_ranking_dir = analysis_dir / "current_category_rankings"
    category_ranking_dir.mkdir(parents=True, exist_ok=True)

    task_rankings_path = task_ranking_dir / "current_selected_task_rankings.json"
    if not task_rankings_path.exists():
        raise FileNotFoundError(f"缺少任务排行榜 JSON: {task_rankings_path}")

    logger.info("=" * 60)
    logger.info("PinchBench-Upgraded 大类排行榜构建（上游 category 自动分组）")
    logger.info("=" * 60)
    logger.info("输入文件: %s", task_rankings_path)
    logger.info("输出目录: %s", category_ranking_dir)

    # ── 1: 读取任务排行榜与翻译表 ─────────────────────────────────────────────
    logger.info("[1/4] 读取任务排行榜与翻译表...")
    category_zh = load_overrides_category_zh(rules_path)
    task_rankings = read_json(task_rankings_path)
    logger.info("  category_zh 翻译条目: %d", len(category_zh))

    # 建任务索引
    task_index: dict[str, dict] = {}
    for task in task_rankings.get("tasks") or []:
        task_index[str(task["task_id"])] = task

    # step3 输出的 models 列表已经只包含 K > 0 的模型（filtered_out 已剔除）
    ranking_models = task_rankings.get("models") or []
    filtered_out_models = task_rankings.get("filtered_out_models") or []

    logger.info("  进入大类表模型数: %d", len(ranking_models))
    logger.info("  筛除模型数（K=0）: %d", len(filtered_out_models))

    # ── 按 task.category 自动分组（来自 step3 输出的归一化小写英文 category）──
    cat_to_task_ids: dict[str, list[str]] = {}
    for task in task_rankings.get("tasks") or []:
        cat = str(task.get("category") or "uncategorized") or "uncategorized"
        cat_to_task_ids.setdefault(cat, []).append(str(task["task_id"]))

    # 稳定顺序：任务数降序 + cat 字母序
    sorted_cats: list[tuple[str, list[str]]] = sorted(
        cat_to_task_ids.items(), key=lambda kv: (-len(kv[1]), kv[0])
    )
    logger.info("  自动得到 %d 个大类: %s", len(sorted_cats),
                ", ".join(f"{c}({len(tids)})" for c, tids in sorted_cats))

    # 预构建 task row 查找索引：(task_id, provider, model) -> row
    _task_row_index: dict[tuple[str, str, str], dict] = {}
    for task in task_index.values():
        tid = str(task["task_id"])
        for r in (task.get("rows") or []):
            _task_row_index[(tid, r["provider"], r["model"])] = r

    # ── 2: 按大类聚合 ─────────────────────────────────────────────────────────
    logger.info("[2/4] 按大类聚合模型指标...")
    category_tables: list[dict] = []

    for cat_en, task_ids_in_cat in sorted_cats:
        cat_zh = category_zh.get(cat_en) or cat_en
        sorted_rows = _aggregate_category_rows(task_ids_in_cat, ranking_models, _task_row_index)

        # 任务清单（含中英文名，模板用）
        task_items: list[dict] = []
        for tid in sorted(task_ids_in_cat):
            t = task_index.get(tid) or {}
            task_items.append({
                "task_id": tid,
                "task_name_en": t.get("task_name", tid),
                "task_name_zh": t.get("task_name_zh") or t.get("task_name", tid),
            })

        category_tables.append({
            "category_name_zh": cat_zh,
            "category_name_en": cat_en,
            "task_count": len(task_ids_in_cat),
            "task_ids": task_ids_in_cat,
            "tasks": task_items,
            "row_count": len(sorted_rows),
            "rows": sorted_rows,
        })

    logger.info("  大类表数量: %d", len(category_tables))
    if category_tables:
        logger.info("  首个大类模型数: %d", category_tables[0]["row_count"])

    # ── 构建「总排行榜」（按大类聚合方案，把全部 canonical 任务视为一个超级大类）──
    all_canonical_tids: list[str] = [tid for _cat, tids in sorted_cats for tid in tids]
    overall_rows = _aggregate_category_rows(all_canonical_tids, ranking_models, _task_row_index)
    overall_table = {
        "category_name_zh": "总排行榜",
        "category_name_en": "Overall Ranking",
        "task_count": len(all_canonical_tids),
        "task_ids": all_canonical_tids,
        "row_count": len(overall_rows),
        "rows": overall_rows,
        "is_overall": True,
    }
    logger.info("  总排行榜模型数: %d（覆盖 %d 项任务）",
                overall_table["row_count"], overall_table["task_count"])

    # ── 3: 构建 all_data_json 并写出 JSON ────────────────────────────────────
    logger.info("[3/4] 构建 all_data_json 并写出 JSON 结果...")

    step3_tasks = task_rankings.get("tasks") or []
    step3_models = task_rankings.get("models") or []

    all_data_models: dict = {}
    for sm in step3_models:
        model_key = f"{sm['provider']}:{sm['model']}"
        all_data_models[model_key] = {
            "name": sm["model"],
            "provider": sm["provider"],
            "is_china": sm.get("is_china_model", False),
            "is_open_weight": sm.get("is_open_weight_model", False),
            "run_count": sm.get("run_count", 0),
            "total_submission_count": sm.get("total_submission_count", 0),
            "model_size_raw": sm.get("model_size_raw"),
            "model_size_b": sm.get("model_size_b"),
        }

    # 构建 all_data["tasks"]
    all_data_tasks: dict = {}
    for t in step3_tasks:
        tid = t["task_id"]
        all_data_tasks[tid] = {
            "name_zh": t.get("task_name_zh") or t.get("task_name", ""),
            "name_en": t.get("task_name", ""),
            "category": t.get("category", "uncategorized"),
            "category_zh": t.get("category_zh", "uncategorized"),
            "grading_type": t.get("grading_type", ""),
            "results": {},
        }
        for r in (t.get("rows") or []):
            model_key = f"{r['provider']}:{r['model']}"
            all_data_tasks[tid]["results"][model_key] = {
                "success_rate": r.get("average_success_rate_pct"),
                "run_count": r.get("run_count", 0),
                "cost": r.get("cost_per_run_usd"),
                "duration": r.get("avg_duration_s"),
                "value_score": r.get("value_score"),
                "time_efficiency": r.get("time_efficiency"),
            }

    # 构建 all_data["categories"]：以归一化英文 cat 为 key
    all_data_categories: dict = {}
    # 「总排行榜」作为一个特殊 key="overall"，覆盖全部 canonical 任务
    all_data_categories["overall"] = {
        "name_zh": "总排行榜",
        "name_en": "Overall Ranking",
        "task_ids": all_canonical_tids,
    }
    for cat_en, task_ids_in_cat in sorted_cats:
        cat_zh = category_zh.get(cat_en) or cat_en
        all_data_categories[cat_en] = {
            "name_zh": cat_zh,
            "name_en": cat_en,
            "task_ids": task_ids_in_cat,
        }

    all_data = {
        "models": all_data_models,
        "tasks": all_data_tasks,
        "categories": all_data_categories,
        "filtered_out_models": filtered_out_models,
        "filtered_out_count": len(filtered_out_models),
        "canonical_task_count": task_rankings.get("canonical_task_count", 0),
        "filter_defaults": {
            "min_obs": FILTER_DEFAULTS["min_obs"],
            "country": FILTER_DEFAULTS["country"],
            "open_source": FILTER_DEFAULTS["open_source"],
            "lang": FILTER_DEFAULTS["lang"],
        },
    }

    category_rankings_data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "source_generated_at": task_rankings.get("source_generated_at"),
        "current_total_models": task_rankings.get("current_total_models"),
        "official_models": task_rankings.get("official_models"),
        "selected_benchmark_versions": task_rankings.get("selected_benchmark_versions") or [],
        "total_valid_submissions": task_rankings.get("total_valid_submissions", 0),
        "total_invalid_submissions": task_rankings.get("total_invalid_submissions", 0),
        "ranking_model_count": task_rankings.get("ranking_model_count"),
        "filtered_out_count": len(filtered_out_models),
        "filtered_out_models": filtered_out_models,
        "canonical_task_count": task_rankings.get("canonical_task_count", 0),
        "category_count": len(category_tables),
        "models": ranking_models,
        "metrics_definition": {
            "source": "基于 current_selected_task_rankings.json 二次聚合，不重复请求 API",
            "category_source": (
                "大类直接来自上游 task.frontmatter.category（归一化小写英文）；"
                "中文名查 rules.overrides_category_zh，缺失回退英文"
            ),
            "run_count": "大类 run_count = K（模型级，跨 task 跨大类相同）",
            "average_success_rate_pct": "大类成功率 = avg(各 task 的 average_success_rate_pct)，单位 %",
            "cost_per_run_usd": (
                "大类成本 = 任务级 cost_per_run_usd × T（T = 大类内 task 数）；"
                "任务级 cost_per_run_usd = sum(submission total_cost_usd) / K / N（N = canonical 全集任务数）；"
                "所以大类成本 = sum(submission_cost) × T / K / N，单位 USD；"
                "总排行榜（T = N）退化为平均一份 submission 的总成本"
            ),
            "avg_duration_min": "大类耗时 = sum(各 task 的 avg_duration_s) / 60，单位分钟；HTML 表格直接显示该值（不再前端换算）",
            "value_score": "大类 value_score = average_success_rate_pct / cost_per_run_usd，单位 %/USD",
            "time_efficiency": "大类 time_efficiency = average_success_rate_pct / avg_duration_min，单位 %/min（每分钟可获得的成功率）",
            "exclusion": "K = 0 的模型已在 step2 标记为 filtered_out，不进入大类表",
        },
        "overall": overall_table,
        "categories": category_tables,
        "all_data_json": json.dumps(all_data, ensure_ascii=False),
    }

    out_json = category_ranking_dir / "current_selected_category_rankings.json"
    json_output = {k: v for k, v in category_rankings_data.items() if k != "all_data_json"}
    write_json(out_json, json_output)

    # ── 4: 写出 HTML ──────────────────────────────────────────────────────────
    logger.info("[4/4] 写出 HTML 结果...")
    out_html = category_ranking_dir / "current_selected_category_rankings.html"
    html_content = render_category_rankings(category_rankings_data)
    out_html.write_text(html_content, encoding="utf-8")

    logger.info("输出文件:")
    logger.info("  %s", out_json)
    logger.info("  %s", out_html)
