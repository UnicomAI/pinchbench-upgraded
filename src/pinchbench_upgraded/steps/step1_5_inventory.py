"""Step 1.5: 版本盘点报告（基于 Step 1 落盘的全量 submissions detail）。

数据源：扫描 ``submissions/current/*.json`` 下全部 submission detail，
按 (model, provider, benchmark_version) 聚合得到该模型在该版本下跑过的
**全部任务并集**，再按 benchmark_version 出报告。
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pinchbench_upgraded.utils import read_json, write_json

logger = logging.getLogger(__name__)


def run(data_dir: Path, rules_path: Path) -> None:
    submissions_dir = data_dir / "submissions" / "current"

    if not submissions_dir.exists():
        raise FileNotFoundError(
            f"缺少 current submission 详情目录: {submissions_dir}\n请先运行 fetch 步骤。"
        )

    output_dir = data_dir / "analysis" / "version_inventory"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "version_inventory_report.json"
    md_path = output_dir / "version_inventory_report.md"

    logger.info("=" * 60)
    logger.info("PinchBench-Upgraded 版本盘点报告生成（基于全量 submissions）")
    logger.info("=" * 60)
    logger.info("详情目录: %s", submissions_dir)

    logger.info("[1/3] 扫描全量 submission 详情...")

    # 按 (model, provider, version) 聚合任务并集与 submission 计数
    per_key_tasks: dict[tuple[str, str, str], set[str]] = {}
    per_key_subcount: dict[tuple[str, str, str], int] = {}
    per_key_official: dict[tuple[str, str, str], bool] = {}

    detail_files = sorted(submissions_dir.glob("*.json"))
    scanned = 0
    skipped = 0

    for f in detail_files:
        try:
            payload = read_json(f)
        except Exception as exc:
            logger.warning("  无法读取 %s: %s", f.name, exc)
            skipped += 1
            continue

        sub = payload.get("submission") or {}
        model = str(sub.get("model") or "")
        provider = str(sub.get("provider") or "")
        version = str(sub.get("benchmark_version") or "") or "(unknown)"
        official_flag = sub.get("official") is True

        key = (model, provider, version)
        per_key_subcount[key] = per_key_subcount.get(key, 0) + 1
        # 只要有一条标记 official=True，整组就视为官方
        per_key_official[key] = per_key_official.get(key, False) or official_flag

        task_set = per_key_tasks.setdefault(key, set())
        for task in sub.get("tasks") or []:
            raw_tid = str(task.get("task_id") or "")
            task_set.add(raw_tid)

        scanned += 1

    logger.info("  扫描 detail 文件: %d 个（跳过 %d 个）", scanned, skipped)
    logger.info("  (model, provider, version) 唯一键: %d 个", len(per_key_tasks))

    # 按 version 分桶
    logger.info("[2/3] 按 benchmark_version 聚合...")
    per_version: dict[str, list[dict]] = {}
    for (model, provider, version), task_set in per_key_tasks.items():
        per_version.setdefault(version, []).append({
            "model": model,
            "provider": provider,
            "is_official": per_key_official.get((model, provider, version), False),
            "task_count": len(task_set),
            "task_ids": sorted(task_set),
            "submission_count": per_key_subcount.get((model, provider, version), 0),
        })

    versions_summary: list[dict] = []
    for vid, entries in per_version.items():
        official_entries = [e for e in entries if e["is_official"]]
        task_distribution_counter = Counter(e["task_count"] for e in official_entries)
        task_distribution = dict(sorted(task_distribution_counter.items(), key=lambda kv: -kv[0]))
        # 任务覆盖：该任务被多少个**模型**跑过（按 (model, provider) 去重，不按 submission 计数）
        task_coverage_counter: Counter[str] = Counter()
        for e in official_entries:
            task_coverage_counter.update(e["task_ids"])
        task_coverage = dict(sorted(
            task_coverage_counter.items(),
            key=lambda kv: (-kv[1], kv[0]),
        ))
        all_task_ids: set[str] = set()
        for e in official_entries:
            all_task_ids.update(e["task_ids"])
        total_subs = sum(e["submission_count"] for e in entries)
        official_subs = sum(e["submission_count"] for e in official_entries)

        versions_summary.append({
            "id": vid,
            "official_model_count": len(official_entries),
            "total_model_count": len(entries),
            "official_submission_count": official_subs,
            "total_submission_count": total_subs,
            "all_task_id_count": len(all_task_ids),
            "task_distribution": task_distribution,
            "task_coverage": task_coverage,
            "all_task_ids": sorted(all_task_ids),
        })

    versions_summary.sort(key=lambda v: (-v["official_model_count"], v["id"]))

    logger.info("[3/3] 写出报告文件...")
    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "submissions_dir": str(submissions_dir),
        "version_count": len(versions_summary),
        "detail_files_scanned": scanned,
        "detail_files_skipped": skipped,
        "unique_keys": len(per_key_tasks),
        "data_basis": "full_submissions",  # 区别于旧版的 "best_submission_only"
        "versions": versions_summary,
    }
    write_json(json_path, report_payload)
    _write_markdown_report(md_path, report_payload)

    logger.info("输出文件:")
    logger.info("  %s", json_path)
    logger.info("  %s", md_path)
    logger.info("=" * 60)
    logger.info("人工决策提示：")
    logger.info("  请阅读 %s", md_path)
    logger.info("  在 %s 中填写 selected_benchmark_versions 与 selected_task_ids", rules_path)
    logger.info("  填写完成后运行 `pinchbench-upgraded scope` 继续后续流程")


def _format_task_distribution(distribution: dict[int, int]) -> str:
    if not distribution:
        return "—"
    return " / ".join(f"{count}:{models}" for count, models in distribution.items())


def _write_markdown_report(md_path: Path, payload: dict) -> None:
    versions: list[dict] = payload["versions"]
    lines: list[str] = []

    lines.append("# PinchBench-Upgraded 版本盘点报告")
    lines.append("")
    lines.append(f"- 生成时间: {payload['generated_at']}")
    lines.append(f"- 数据目录: `{payload['data_dir']}`")
    lines.append(f"- 数据基础: **全量 submissions**（每模型在该版本下跑过的所有 submission 任务并集）")
    lines.append(f"- 已扫描 detail 文件: {payload['detail_files_scanned']}（跳过 {payload['detail_files_skipped']}）")
    lines.append(f"- (model, provider, version) 唯一键: {payload['unique_keys']}")
    lines.append(f"- benchmark_version 数: {payload['version_count']}")
    lines.append("")

    # 1. 版本概览
    lines.append("## 1. 版本概览")
    lines.append("")
    lines.append("| 版本 ID | 官方模型 | 全部模型 | 官方 submissions | 全部 submissions | 独有任务总数 | 任务集分布（任务并集大小:模型数） |")
    lines.append("|---------|----------|----------|------------------|------------------|--------------|-----------------------------------|")
    for v in versions:
        lines.append(
            f"| `{v['id']}` | {v['official_model_count']} | {v['total_model_count']} "
            f"| {v['official_submission_count']} | {v['total_submission_count']} "
            f"| {v['all_task_id_count']} | {_format_task_distribution(v['task_distribution'])} |"
        )
    lines.append("")
    lines.append("> 「任务集分布」基于每个模型在该版本下跑过的**全部 submission 任务并集**——比基于 best 单条更稳健。")
    lines.append("")

    # 2. 任务覆盖明细
    lines.append("## 2. 任务覆盖明细（按版本，覆盖模型数 = 在该版本下至少跑过一次该任务的官方模型数）")
    lines.append("")
    for v in versions:
        m = v["official_model_count"]
        if m == 0:
            continue
        lines.append(
            f"### 版本 `{v['id']}`（官方模型 {m} 个，独有任务 {v['all_task_id_count']} 个，"
            f"官方 submissions {v['official_submission_count']} 条）"
        )
        lines.append("")
        lines.append("| 任务 ID | 覆盖模型数 | 占比 |")
        lines.append("|---------|------------|------|")
        for tid, cnt in v["task_coverage"].items():
            ratio = cnt / m if m > 0 else 0
            lines.append(f"| `{tid}` | {cnt} | {ratio:.0%} |")
        lines.append("")

    # 3. 操作指引
    lines.append("## 3. 操作指引")
    lines.append("")
    lines.append("将以下两个字段填入 `current_model_scope_rules.json`（项目根目录），再运行 `pinchbench-upgraded scope`：")
    lines.append("")
    lines.append("```json")
    lines.append("{")
    if versions:
        recommended = versions[0]
        sample_canonical = list(recommended["task_coverage"].keys())[:3]
        lines.append(f'  "selected_benchmark_versions": ["{recommended["id"]}"],')
        joined = ", ".join(f'"{t}"' for t in sample_canonical)
        ellipsis = ", ..." if len(recommended["task_coverage"]) > 3 else ""
        lines.append(f'  "selected_task_ids": [{joined}{ellipsis}]')
    else:
        lines.append('  "selected_benchmark_versions": [],')
        lines.append('  "selected_task_ids": []')
    lines.append("}")
    lines.append("```")
    lines.append("")
    lines.append("### 选择策略")
    lines.append("")
    lines.append("- **完整集**：取选定版本所有任务（数据量最大，覆盖度低的模型会被剔除）")
    lines.append("- **兼容集**：取选定版本内所有官方模型都跑过的任务（数据量小，模型保留率高）")
    lines.append("- **覆盖率门槛**：选取覆盖模型数 ≥ 选定版本官方模型数 50% 的任务（折中方案）")
    lines.append("")
    lines.append(
        "Step 2 对每条 submission 做四条件二元有效性判定：①版本匹配 "
        "②submission 的 task_id 集合精确等于 canonical 集合 "
        "③`total_cost_usd > 0` ④每个 task 的 `execution_time_seconds > 0`；"
        "任意失败则该 submission 整体失效，按 "
        "`canonical_extra > canonical_missing > task_time_zero > cost_zero` 单一归类。"
        "模型的 valid submission 数 K=0 时进入「筛除模型」区——"
        "选 canonical 时应避开覆盖过低的任务，否则少数模型会因 canonical_missing 被淘汰。"
    )
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
