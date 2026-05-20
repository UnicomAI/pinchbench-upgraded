"""Step 3: 任务排行榜（基于 K 份 valid submission 直接累加）。

数据流：
- step2 已对每条 submission 做二元有效性判定，产出 valid_submission_ids 等字段
- step3 只需要：对每个 K > 0 的模型，按 K 份 valid submission 直接累加各 task 指标
- 任务级公式：
    run_count    = K
    success_rate = sum(score / max_score × 100) / K
    cost         = sum(submission total_cost_usd) / K / N  ← 单 task 摊到的成本
    duration     = sum(execution_time_seconds) / K
    value_score  = success_rate / cost
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from pinchbench_upgraded.cache import SubmissionCache
from pinchbench_upgraded.config import (
    FILTER_DEFAULTS,
    load_overrides_category_zh,
    load_overrides_task_zh,
)
from pinchbench_upgraded.html.renderer import render_task_rankings
from pinchbench_upgraded.utils import read_json, read_json_list, write_json, sort_ranking_rows

logger = logging.getLogger(__name__)


def run(data_dir: Path, rules_path: Path) -> None:
    analysis_dir = data_dir / "analysis"
    scope_dir = analysis_dir / "current_model_scope"
    task_ranking_dir = analysis_dir / "current_task_rankings"
    task_ranking_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = scope_dir / "current_model_inventory.json"
    scope_summary_path = scope_dir / "current_model_scope_summary.json"

    for p, desc in [
        (inventory_path, "step2 inventory 文件"),
        (scope_summary_path, "step2 scope summary 文件"),
    ]:
        if not p.exists():
            raise FileNotFoundError(f"缺少{desc}: {p}\n请先运行 `pinchbench-upgraded scope`")

    logger.info("=" * 60)
    logger.info("PinchBench-Upgraded 任务排行榜构建")
    logger.info("=" * 60)

    inventory = read_json_list(inventory_path)
    scope_summary = read_json(scope_summary_path)

    logger.info("[1/5] 读取 step2 产物...")
    logger.info("  inventory 模型数: %d", len(inventory))

    cache = SubmissionCache(data_dir)

    # 翻译表
    category_zh = load_overrides_category_zh(rules_path)
    task_name_zh = load_overrides_task_zh(rules_path)
    logger.info("  category_zh 翻译条目: %d", len(category_zh))
    logger.info("  task_name_zh 翻译条目: %d", len(task_name_zh))

    canonical_task_ids: list[str] = scope_summary.get("canonical_task_ids") or []
    canonical_set: set[str] = set(canonical_task_ids)
    N = len(canonical_set)  # 总任务数，用于成本归一化
    if N == 0:
        raise ValueError("scope_summary.canonical_task_ids 为空，无法构建任务排行榜")
    logger.info("  canonical 任务数 N: %d", N)

    # 仅处理官方且 valid_submission_count > 0 的模型
    ranking_models = [
        r for r in inventory
        if r.get("official") and int(r.get("valid_submission_count") or 0) > 0
    ]
    filtered_out_models = [
        {
            "model": r["model"],
            "provider": r["provider"],
            "invalid_reasons": r.get("invalid_reasons") or {},
            "sample_invalid_submissions": r.get("sample_invalid_submissions") or [],
        }
        for r in inventory
        if r.get("official") and int(r.get("valid_submission_count") or 0) == 0
    ]
    logger.info("  进入排行榜模型数: %d", len(ranking_models))
    logger.info("  筛除模型数（valid_submission_count = 0）: %d", len(filtered_out_models))

    # ── Step 2: 对每个 ranking 模型读取其 K 份 valid submission 详情并聚合 ──
    logger.info("[2/5] 读取 K 份 valid submission 详情并聚合任务级指标...")
    global_task_catalog: dict[str, dict] = {}  # tid -> {task_id, task_name, category, grading_type}
    model_task_metrics: list[dict] = []        # 每个模型一项：含 K + 各 task 累加结果

    for i, model_row in enumerate(ranking_models):
        model_id = str(model_row["model"])
        provider_id = str(model_row["provider"])
        valid_ids: list[str] = model_row.get("valid_submission_ids") or []
        K = len(valid_ids)

        # 该模型的累加器：tid -> {sum_score_pct, sum_duration_s}
        per_task_sum: dict[str, dict] = {}
        sum_total_cost_usd = 0.0  # 跨 K 份 submission 的 cost 累加

        for sub_id in valid_ids:
            detail = cache.get_submission_detail(sub_id)
            if detail is None:
                raise FileNotFoundError(
                    f"缺少 submission detail 缓存（{sub_id}）：请重新运行 `pinchbench-upgraded fetch`"
                )
            run_sub = detail.get("submission") or {}
            usage = run_sub.get("usage_summary") or {}
            sub_cost = float(usage.get("total_cost_usd") or 0)
            sum_total_cost_usd += sub_cost

            for task in run_sub.get("tasks") or []:
                raw_tid = str(task.get("task_id") or "")
                if not raw_tid or raw_tid not in canonical_set:
                    # 严格匹配已保证 submission.tasks 恰好 == canonical_set，
                    # 这里仍防御性跳过非 canonical 任务
                    continue
                frontmatter = task.get("frontmatter") or {}
                tname = frontmatter.get("name") or raw_tid
                tcat = frontmatter.get("category") or None
                tgrad = task.get("grading_type") or None

                if raw_tid not in global_task_catalog:
                    cat_lower = (str(tcat).strip().lower() if tcat else "") or "uncategorized"
                    global_task_catalog[raw_tid] = {
                        "task_id": raw_tid,
                        "task_name": tname,
                        "category": cat_lower,
                        "grading_type": tgrad,
                    }

                if raw_tid not in per_task_sum:
                    per_task_sum[raw_tid] = {"sum_score_pct": 0.0, "sum_duration_s": 0.0}

                max_score = task.get("max_score") or 0
                score = task.get("score") or 0
                exec_time = task.get("execution_time_seconds") or 0
                if max_score > 0:
                    per_task_sum[raw_tid]["sum_score_pct"] += (float(score) / float(max_score)) * 100
                per_task_sum[raw_tid]["sum_duration_s"] += float(exec_time)

        progress = round((i + 1) / len(ranking_models) * 100, 1)
        logger.info("  [%d/%d] (%.1f%%) %s | K=%d | cost_sum=%.4f",
                    i + 1, len(ranking_models), progress, model_id, K, sum_total_cost_usd)

        invalid_sum = sum((model_row.get("invalid_reasons") or {}).values())
        model_task_metrics.append({
            "model": model_id,
            "provider": provider_id,
            "K": K,
            "total_submission_count": K + invalid_sum,  # 选定版本下：valid + invalid
            "sum_total_cost_usd": sum_total_cost_usd,
            "model_size_raw": model_row.get("model_size_raw"),
            "model_size_b": model_row.get("model_size_b"),
            "is_open_weight_model": bool(model_row.get("is_open_weight_model")),
            "is_china_model": bool(model_row.get("is_china_model")),
            "per_task_sum": per_task_sum,
        })

    # ── Step 3: 计算任务级指标 ──────────────────────────────────────────────
    logger.info("[3/5] 计算任务级指标（每个 task × 每个模型）...")
    task_ids_sorted = sorted(global_task_catalog.keys())

    # 任务级单值（同一模型跨 task 相同）：成本 / K / N
    def _task_cost(mrd: dict) -> float | None:
        if mrd["K"] <= 0 or N <= 0:
            return None
        return mrd["sum_total_cost_usd"] / mrd["K"] / N

    def _compute_task_row(mrd: dict, tid: str) -> dict:
        K = mrd["K"]
        per_t = mrd["per_task_sum"].get(tid)
        if not per_t or K <= 0:
            return {
                "rank": None,
                "model": mrd["model"],
                "provider": mrd["provider"],
                "model_size_raw": mrd["model_size_raw"],
                "model_size_b": mrd["model_size_b"],
                "average_success_rate_pct": None,
                "run_count": K,
                "cost_per_run_usd": None,
                "avg_duration_s": None,
                "value_score": None,
                "time_efficiency": None,
            }
        avg_success = round(per_t["sum_score_pct"] / K, 2)
        avg_duration_s = round(per_t["sum_duration_s"] / K, 2)
        cost = _task_cost(mrd)
        cost_rounded = round(cost, 4) if cost is not None else None
        value_score = (
            round(avg_success / cost, 2)
            if cost is not None and cost > 0 else None
        )
        time_efficiency = (
            round(avg_success / avg_duration_s, 2)
            if avg_duration_s is not None and avg_duration_s > 0 else None
        )
        return {
            "rank": None,
            "model": mrd["model"],
            "provider": mrd["provider"],
            "model_size_raw": mrd["model_size_raw"],
            "model_size_b": mrd["model_size_b"],
            "average_success_rate_pct": avg_success,
            "run_count": K,
            "cost_per_run_usd": cost_rounded,
            "avg_duration_s": avg_duration_s,
            "value_score": value_score,
            "time_efficiency": time_efficiency,
        }

    task_tables_all: list[dict] = []
    for tid in task_ids_sorted:
        meta = global_task_catalog[tid]
        rows = [_compute_task_row(mrd, tid) for mrd in model_task_metrics]
        sorted_rows = sort_ranking_rows(rows)
        for rank_i, r in enumerate(sorted_rows):
            r["rank"] = rank_i + 1
        cat_en = meta["category"] or "uncategorized"
        cat_zh = category_zh.get(cat_en) or cat_en
        task_tables_all.append({
            "task_id": meta["task_id"],
            "task_name": meta["task_name"],
            "task_name_zh": task_name_zh.get(meta["task_id"], meta["task_name"]),
            "category": cat_en,
            "category_zh": cat_zh,
            "grading_type": meta["grading_type"],
            "row_count": len(sorted_rows),
            "rows": sorted_rows,
        })
    logger.info("  任务表数量: %d", len(task_tables_all))

    # ── Step 4: 构建 models_summary、默认筛选、categories ──────────────────
    models_summary: list[dict] = []
    for mrd in sorted(model_task_metrics, key=lambda r: (r["provider"], r["model"])):
        models_summary.append({
            "provider": mrd["provider"],
            "model": mrd["model"],
            "model_size_raw": mrd["model_size_raw"],
            "model_size_b": mrd["model_size_b"],
            "is_open_weight_model": mrd["is_open_weight_model"],
            "is_china_model": mrd["is_china_model"],
            "is_open_weight_and_china": (
                mrd["is_open_weight_model"] and mrd["is_china_model"]
            ),
            "run_count": mrd["K"],
            "total_submission_count": mrd["total_submission_count"],
            "sum_total_cost_usd": round(mrd["sum_total_cost_usd"], 4),
        })

    # 默认筛选：与 base.html JS 漏斗对齐（国别 / 开源 / 运行次数）
    min_obs_default = FILTER_DEFAULTS["min_obs"]
    country_default = FILTER_DEFAULTS["country"]
    open_default = FILTER_DEFAULTS["open_source"]

    def _passes_country(sm: dict) -> bool:
        if country_default == "china":
            return bool(sm["is_china_model"])
        if country_default == "other":
            return not sm["is_china_model"]
        return True

    def _passes_open(sm: dict) -> bool:
        if open_default == "open":
            return bool(sm["is_open_weight_model"])
        if open_default == "closed":
            return not sm["is_open_weight_model"]
        return True

    default_model_keys: set[str] = set()
    default_models_summary: list[dict] = []
    for sm in models_summary:
        key = f"{sm['provider']}:{sm['model']}"
        if _passes_country(sm) and _passes_open(sm) and sm["run_count"] >= min_obs_default:
            default_model_keys.add(key)
            default_models_summary.append(sm)
    logger.info("  默认视图模型数（运行次数 >= %d）: %d", min_obs_default, len(default_model_keys))

    # 过滤后的任务表
    task_tables_default: list[dict] = []
    for t in task_tables_all:
        filtered_rows = [r for r in t["rows"]
                         if f"{r['provider']}:{r['model']}" in default_model_keys]
        re_sorted = sort_ranking_rows(filtered_rows)
        for rank_i, r in enumerate(re_sorted):
            r["rank"] = rank_i + 1
        task_tables_default.append({
            **t,
            "row_count": len(re_sorted),
            "rows": re_sorted,
        })

    # categories：按上游 category 自动分组
    cat_to_task_ids: dict[str, list[str]] = {}
    for t in task_tables_all:
        cat = str(t.get("category") or "uncategorized") or "uncategorized"
        cat_to_task_ids.setdefault(cat, []).append(t["task_id"])
    sorted_cats = sorted(cat_to_task_ids.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    categories_for_template: list[dict] = []
    for cat_en, tids in sorted_cats:
        cat_zh = category_zh.get(cat_en) or cat_en
        task_items = []
        for tid in sorted(tids):
            meta = global_task_catalog.get(tid) or {}
            tname_en = meta.get("task_name", tid)
            task_items.append({
                "task_id": tid,
                "task_name_en": tname_en,
                "task_name_zh": task_name_zh.get(tid, tname_en),
            })
        categories_for_template.append({
            "category_name_zh": cat_zh,
            "category_name_en": cat_en,
            "task_count": len(tids),
            "tasks": task_items,
        })

    # ── 构建 all_data_json（前端动态筛选用）────────────────────────────────
    all_data: dict = {
        "models": {},
        "tasks": {},
        "filtered_out_models": filtered_out_models,
        "filtered_out_count": len(filtered_out_models),
        "canonical_task_count": N,
        "filter_defaults": {
            "min_obs": FILTER_DEFAULTS["min_obs"],
            "country": FILTER_DEFAULTS["country"],
            "open_source": FILTER_DEFAULTS["open_source"],
            "lang": FILTER_DEFAULTS["lang"],
        },
    }
    for sm in models_summary:
        model_key = f"{sm['provider']}:{sm['model']}"
        all_data["models"][model_key] = {
            "name": sm["model"],
            "provider": sm["provider"],
            "is_china": sm["is_china_model"],
            "is_open_weight": sm["is_open_weight_model"],
            "run_count": sm["run_count"],
            "total_submission_count": sm["total_submission_count"],
            "model_size_raw": sm.get("model_size_raw"),
            "model_size_b": sm.get("model_size_b"),
        }
    for t in task_tables_all:
        tid = t["task_id"]
        all_data["tasks"][tid] = {
            "name_zh": t["task_name_zh"],
            "name_en": t["task_name"],
            "category": t["category"],
            "category_zh": t["category_zh"],
            "grading_type": t["grading_type"],
            "results": {},
        }
        for r in t["rows"]:
            model_key = f"{r['provider']}:{r['model']}"
            all_data["tasks"][tid]["results"][model_key] = {
                "success_rate": r["average_success_rate_pct"],
                "run_count": r["run_count"],
                "cost": r["cost_per_run_usd"],
                "duration": r["avg_duration_s"],
                "value_score": r["value_score"],
                "time_efficiency": r.get("time_efficiency"),
            }

    # ── Step 4: 写出 JSON ─────────────────────────────────────────────────────
    logger.info("[4/5] 写出 JSON 结果...")
    task_rankings_data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "source_generated_at": scope_summary.get("generated_at"),
        "current_total_models": scope_summary.get("current_total_models"),
        "official_models": scope_summary.get("official_models"),
        "selected_benchmark_versions": scope_summary.get("selected_benchmark_versions") or [],
        "total_valid_submissions": scope_summary.get("total_valid_submissions", 0),
        "total_invalid_submissions": scope_summary.get("total_invalid_submissions", 0),
        "ranking_model_count": len(ranking_models),
        "filtered_out_count": len(filtered_out_models),
        "filtered_out_models": filtered_out_models,
        "canonical_task_count": N,
        "task_count": len(task_tables_all),
        "output_sorting": (
            "按 average_success_rate_pct 从高到低；同分按 value_score、avg_duration_s、model 稳定排序"
        ),
        "metrics_definition": {
            "run_count": "模型的有效 submission 数（K），跨 task 跨大类相同",
            "average_success_rate_pct": "sum(每份 valid submission 该 task 的 score / max_score × 100) / K，单位 %",
            "cost_per_run_usd": (
                "sum(每份 valid submission 的 usage_summary.total_cost_usd) / K / N，"
                "单位 USD per task；N = canonical 总任务数，所以是单 task 摊到的平均成本"
            ),
            "avg_duration_s": "sum(每份 valid submission 该 task 的 execution_time_seconds) / K，单位秒；任务级 HTML 直接显示秒",
            "value_score": "average_success_rate_pct / cost_per_run_usd，单位 %/USD",
            "time_efficiency": "average_success_rate_pct / avg_duration_s，单位 %/s（每秒可获得的成功率）",
        },
        "models": models_summary,
        "categories": categories_for_template,
        "tasks": task_tables_all,
        "all_data_json": json.dumps(all_data, ensure_ascii=False),
    }

    out_json = task_ranking_dir / "current_selected_task_rankings.json"
    json_output = {k: v for k, v in task_rankings_data.items() if k != "all_data_json"}
    write_json(out_json, json_output)

    # ── Step 5: 写出 HTML ─────────────────────────────────────────────────────
    logger.info("[5/5] 写出 HTML 结果...")
    out_html = task_ranking_dir / "current_selected_task_rankings.html"
    html_data = dict(task_rankings_data)
    html_data["models"] = default_models_summary
    html_data["filtered_out_models"] = filtered_out_models
    html_data["categories"] = categories_for_template
    html_data["tasks"] = task_tables_default
    html_data["selected_model_count"] = len(default_models_summary)
    html_data["ranking_model_count"] = len(default_models_summary)
    html_data["filtered_out_count"] = len(filtered_out_models)
    html_data["canonical_task_count"] = N
    html_data["task_count"] = len(task_tables_default)
    html_content = render_task_rankings(html_data)
    out_html.write_text(html_content, encoding="utf-8")

    logger.info("输出文件:")
    logger.info("  %s", out_json)
    logger.info("  %s", out_html)
