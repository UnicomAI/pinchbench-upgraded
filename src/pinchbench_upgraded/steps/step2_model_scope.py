"""Step 2: 筛选模型范围（submission 级二元有效性）。

数据模型核心：
- 一份 submission 视为有效 ⟺ 同时满足 4 条：
  1. benchmark_version ∈ selected_versions
  2. set(submission.tasks[*].task_id) == canonical_set（集合相等）
  3. usage_summary.total_cost_usd > 0
  4. 所有 task 的 execution_time_seconds > 0
- 失效按优先级单一归类：canonical_extra > canonical_missing > version_mismatch > task_time_zero > cost_zero
- 模型级 run_count = valid_submission_count；K=0 的模型进入「筛除模型」
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from pinchbench_upgraded.cache import SubmissionCache
from pinchbench_upgraded.utils import read_json, write_json

logger = logging.getLogger(__name__)

_RULES_NOTES = {
    "overrides_china_prefixes": (
        "人工确认的中国模型前缀。代码只读不写。"
        "scope 不会向这里增删条目，可以包含已下线版本中的前缀（幽灵保留）。"
        "人工审核 candidates_china_prefixes 后，请把确认属于中国的前缀手动加进这里。"
    ),
    "candidates_china_prefixes": (
        "由 scope 自动重生：选中版本下观测到所有非 overrides_china_prefixes 的厂商前缀。"
        "每项附 official_models 供人工判断。代码不会把这里的条目自动晋升到 overrides。"
    ),
    "overrides_model_size": (
        "人工确认的模型参数量。代码只读不写。"
        "scope 不会向这里增删条目，可以包含已下线模型（幽灵保留）。"
        "如果模型在这里，则用这里的 model_size_raw / model_size_b 作为最终值；否则视为未知（HTML 显示 -）。"
    ),
    "candidates_model_size": (
        "由 scope 自动重生：选中版本下观测到所有非 overrides_model_size 的模型。"
        "每项附 suggested_model_size_raw / suggested_model_size_b / detected_from 供人工参考。"
        "未检测出参数量的也在这里（detected_from=null），需要人工填具体值后再加到 overrides。"
    ),
    "overrides_is_open_weight": (
        "人工确认的开源模型清单（list[str]）。代码只读不写。"
        "在这个列表里 → is_open_weight=true；否则 → false（无视上游 weights / hf_link）。"
        "scope 不会向这里增删条目，可以包含已下线模型（幽灵保留）。"
    ),
    "candidates_is_open_weight": (
        "由 scope 自动重生：选中版本下观测到所有非 overrides_is_open_weight 的模型。"
        "每项附 upstream_weights / upstream_hf_link 实录供人工参考。"
    ),
    "overrides_category_zh": (
        "人工确认的大类英文 → 中文翻译表。代码只读不写。"
        "命中此表 → HTML 用此表中文名；否则 → HTML 显示英文原名（无 fallback）。"
        "scope 不会向这里增删条目，可以包含已下线分类。"
    ),
    "candidates_category_zh": (
        "由 scope 自动重生：选中版本下观测到所有非 overrides_category_zh 的 category。"
        "上游新增没填 frontmatter.category 的 task 时，'uncategorized' 会作为候选出现，等待人工翻译。"
    ),
    "overrides_task_zh": (
        "人工确认的 task_id → 中文任务名翻译表。代码只读不写。"
        "命中此表 → HTML 用此表中文名；否则 → HTML 显示英文原名。"
        "scope 不会向这里增删条目，可以包含已下线任务。"
    ),
    "candidates_task_zh": (
        "由 scope 自动重生：选中版本下观测到所有非 overrides_task_zh 的 task_id。"
        "每项含 task_id、英文 task_name 与归一化后的 category。"
    ),
    "selected_benchmark_versions": (
        "人工指定的 benchmark_version 列表（hash 或 semver）。Step 2 只处理 submission.benchmark_version "
        "落在此列表的 submission；其余被前置过滤。空数组 → step2 报错。"
        "请先运行 `pinchbench-upgraded inventory` 阅读 version_inventory_report.md 再据此填写。"
    ),
    "selected_task_ids": (
        "人工指定的 canonical 任务全集。Step 2 对每条 submission 做集合相等判定："
        "set(submission.tasks[*].task_id) == set(selected_task_ids) → 有效，否则按差集归类失效。"
        "应是 selected_benchmark_versions 选中版本所有任务的子集。空数组 → step2 报错。"
    ),
}

_COMPOUND_MODEL_SIZE_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)b-(a\d+(?:\.\d+)?)b")
_SIMPLE_MODEL_SIZE_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)b(?![a-z0-9])")


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _model_prefix(model_id: str) -> Optional[str]:
    if not model_id:
        return None
    parts = model_id.split("/", 1)
    return f"{parts[0]}/" if len(parts) >= 2 else model_id


def _starts_with_any(value: str, prefixes: list[str]) -> bool:
    v = value.lower()
    return any(v.startswith(p.lower()) for p in prefixes)


# 版本不匹配由调用方前置过滤掉，不再作为失效原因记入
_INVALID_REASONS_ORDERED = (
    "canonical_extra",
    "canonical_missing",
    "task_time_zero",
    "cost_zero",
)


_SAMPLE_TASK_LIMIT = 5


def _add_task_diag(sample: dict, key: str, items: Optional[set[str]]) -> None:
    """若 items 非空，向 sample 追加截断后的 key 列表与可选的 _truncated 标记。"""
    if not items:
        return
    sample[key] = sorted(items)[:_SAMPLE_TASK_LIMIT]
    if len(items) > _SAMPLE_TASK_LIMIT:
        sample[f"{key}_truncated"] = True


def _classify_submission(
    submission: dict,
    canonical_set: set[str],
) -> tuple[bool, Optional[str], Optional[set[str]], Optional[set[str]]]:
    """对单条 submission 做二元有效性判定（**调用方需保证 submission 已属选定版本**）。

    返回 (is_valid, reason_code_or_None, missing_tasks_or_None, extra_tasks_or_None)。
    缺失/多余的 task_id 用于 sample_invalid_submissions 的诊断细节。

    按优先级单一归类：canonical_extra > canonical_missing > task_time_zero > cost_zero
    """
    sub_task_ids: set[str] = set()
    for task in submission.get("tasks") or []:
        raw_tid = str(task.get("task_id") or "")
        if raw_tid:
            sub_task_ids.add(raw_tid)

    extra = sub_task_ids - canonical_set
    missing = canonical_set - sub_task_ids
    if extra:
        return False, "canonical_extra", None, extra
    if missing:
        return False, "canonical_missing", missing, None

    for task in submission.get("tasks") or []:
        exec_time = task.get("execution_time_seconds")
        if exec_time is None or float(exec_time) <= 0:
            return False, "task_time_zero", None, None

    usage = submission.get("usage_summary") or {}
    total_cost = usage.get("total_cost_usd")
    if total_cost is None or float(total_cost) <= 0:
        return False, "cost_zero", None, None

    return True, None, None, None


def _detect_model_size_from_text(text: Optional[str]) -> tuple[Optional[str], Optional[float]]:
    if not text:
        return None, None

    compound_match = _COMPOUND_MODEL_SIZE_RE.search(text)
    if compound_match:
        return compound_match.group(0).lower(), float(compound_match.group(1))

    simple_match = _SIMPLE_MODEL_SIZE_RE.search(text)
    if simple_match:
        return simple_match.group(0).lower(), float(simple_match.group(1))

    return None, None


def _detect_model_size(model_id: str, hf_link: Optional[str]) -> tuple[Optional[str], Optional[float], Optional[str]]:
    model_raw, model_size_b = _detect_model_size_from_text(model_id)
    if model_size_b is not None:
        return model_raw, model_size_b, "model"

    hf_link_raw, hf_link_size_b = _detect_model_size_from_text(hf_link)
    if hf_link_size_b is not None:
        return hf_link_raw, hf_link_size_b, "hf_link"

    return None, None, None


def _scan_step1_task_catalog(
    submissions_dir: Path,
    selected_versions_set: set[str],
) -> dict[str, tuple[str, str]]:
    """扫描 step1 detail 缓存，仅限 selected_benchmark_versions 命中的 submission。

    返回 ``{task_id: (name_en, category_lower)}``。
    category 已用 ``.lower().strip()`` 归一化（如 ``Research`` → ``research``）；
    没填 frontmatter.category 的 task 归到 ``"uncategorized"`` 桶。
    """
    catalog: dict[str, tuple[str, str]] = {}
    if not submissions_dir.exists():
        return catalog
    for f in submissions_dir.glob("*.json"):
        try:
            d = read_json(f)
        except Exception:
            continue
        sub = d.get("submission") if isinstance(d, dict) else None
        if not isinstance(sub, dict):
            continue
        # 按 selected_benchmark_versions 前置过滤
        sub_version = sub.get("benchmark_version")
        if sub_version not in selected_versions_set:
            continue
        for task in sub.get("tasks") or []:
            raw_tid = str(task.get("task_id") or "")
            if not raw_tid:
                continue
            frontmatter = task.get("frontmatter") or {}
            tname = frontmatter.get("name") or raw_tid
            tcat = frontmatter.get("category") or None
            cat_lower = (str(tcat).strip().lower() if tcat else "") or "uncategorized"
            if raw_tid not in catalog:
                catalog[raw_tid] = (str(tname or ""), cat_lower)
    return catalog


def _default_rules() -> dict:
    """首次生成规则文件时使用的种子结构。所有 overrides_* 与 selected_* 均为空——
    首次跑 scope 后 candidates_* 会列出全部观测项等待人工逐条审核。"""
    return {
        "overrides_china_prefixes": [],
        "candidates_china_prefixes": [],
        "overrides_model_size": {},
        "candidates_model_size": [],
        "overrides_is_open_weight": [],
        "candidates_is_open_weight": [],
        "overrides_category_zh": {},
        "candidates_category_zh": [],
        "overrides_task_zh": {},
        "candidates_task_zh": [],
        "selected_benchmark_versions": [],
        "selected_task_ids": [],
        "notes": dict(_RULES_NOTES),
    }


def _normalize_model_size_override(entry: object) -> tuple[Optional[str], Optional[float]]:
    if not isinstance(entry, dict):
        return None, None

    raw_value = entry.get("model_size_raw")
    model_size_raw = str(raw_value).strip() if raw_value is not None else ""
    model_size_raw = model_size_raw or None

    size_value = entry.get("model_size_b")
    try:
        model_size_b = float(size_value) if size_value is not None else None
    except (TypeError, ValueError):
        model_size_b = None

    return model_size_raw, model_size_b


def _get_overrides_is_open_weight(raw_rules: dict) -> set[str]:
    """返回 ``set[model_id]``。值类型必须为 list；元素为空字符串则忽略。"""
    raw = raw_rules.get("overrides_is_open_weight")
    if not isinstance(raw, list):
        return set()
    return {str(m).strip() for m in raw if str(m).strip()}


def _get_overrides_model_size(raw_rules: dict) -> dict[str, dict]:
    """返回 ``{model_id: {model_size_raw, model_size_b}}``。"""
    overrides = raw_rules.get("overrides_model_size")
    if not isinstance(overrides, dict):
        return {}
    normalized: dict[str, dict] = {}
    for model_id, value in overrides.items():
        key = str(model_id).strip()
        if not key:
            continue
        model_size_raw, model_size_b = _normalize_model_size_override(value)
        normalized[key] = {
            "model_size_raw": model_size_raw,
            "model_size_b": model_size_b,
        }
    return normalized


def _resolve_model_size(
    model_id: str,
    overrides_model_size: dict[str, dict],
) -> tuple[Optional[str], Optional[float]]:
    """纯 overrides 查表：未命中 → (None, None)。"""
    entry = overrides_model_size.get(model_id)
    if entry is None:
        return None, None
    return entry.get("model_size_raw"), entry.get("model_size_b")


def _load_rules(rules_path: Path) -> tuple[list[str], dict, bool]:
    """加载规则文件，返回 (overrides_china_prefixes, raw_rules, rules_existed_before_run)。

    rules.json 不存在时落地一份空种子（所有 overrides_* / selected_* 为空），
    candidates_* 由本次 scope 自动填齐。
    """
    if not rules_path.exists():
        default = _default_rules()
        write_json(rules_path, default)
        return [], default, False

    raw = read_json(rules_path)
    if not isinstance(raw, dict):
        raw = _default_rules()
    prefixes_raw = raw.get("overrides_china_prefixes") or []
    prefixes = sorted(set(
        str(p).strip() for p in prefixes_raw if p and str(p).strip()
    ))
    return prefixes, raw, True


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run(data_dir: Path, rules_path: Path) -> None:
    analysis_dir = data_dir / "analysis"
    scope_dir = analysis_dir / "current_model_scope"
    submissions_current_dir = data_dir / "submissions" / "current"
    leaderboard_current_path = data_dir / "leaderboard_current.json"

    for d in (analysis_dir, scope_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 删除旧格式遗留文件（.csv / .md）
    for legacy in (
        scope_dir / "current_model_inventory.csv",
        scope_dir / "current_selected_models.csv",
        scope_dir / "current_model_scope_summary.md",
        scope_dir / "current_model_scope_maintenance.json",
    ):
        if legacy.exists():
            legacy.unlink()

    if not leaderboard_current_path.exists():
        raise FileNotFoundError(
            f"缺少 current 榜单文件: {leaderboard_current_path}\n请先运行 fetch 步骤。"
        )
    if not submissions_current_dir.exists():
        raise FileNotFoundError(
            f"缺少 current submission 详情目录: {submissions_current_dir}\n请先运行 fetch 步骤。"
        )

    china_prefixes, raw_rules, rules_existed_before_run = _load_rules(rules_path)
    overrides_model_size = _get_overrides_model_size(raw_rules)
    overrides_is_open_weight = _get_overrides_is_open_weight(raw_rules)

    selected_versions_raw = raw_rules.get("selected_benchmark_versions")
    canonical_override_raw = raw_rules.get("selected_task_ids")
    selected_versions: list[str] = (
        [str(v).strip() for v in selected_versions_raw if str(v).strip()]
        if isinstance(selected_versions_raw, list) else []
    )
    canonical_override: list[str] = (
        [str(t).strip() for t in canonical_override_raw if str(t).strip()]
        if isinstance(canonical_override_raw, list) else []
    )

    cache = SubmissionCache(data_dir)

    logger.info("=" * 60)
    logger.info("PinchBench-Upgraded current 模型范围构建")
    logger.info("=" * 60)
    logger.info("输入文件: %s", leaderboard_current_path)
    logger.info("规则文件: %s", rules_path)

    if not selected_versions:
        raise ValueError(
            "rules 文件未指定 selected_benchmark_versions（数组为空）。\n"
            "请先运行 `pinchbench-upgraded inventory` 生成版本盘点报告，然后在\n"
            f"  {rules_path}\n"
            "中填入 selected_benchmark_versions 与 selected_task_ids。"
        )
    if not canonical_override:
        raise ValueError(
            "rules 文件未指定 selected_task_ids（数组为空）。\n"
            "请参考 inventory 报告的『任务覆盖明细』选取 canonical 任务清单。"
        )
    logger.info("人工决策：选定版本 %d 个，canonical 任务 %d 个",
                len(selected_versions), len(canonical_override))

    # ── Step 1: 读取榜单 ──────────────────────────────────────────────────────
    logger.info("[1/5] 读取 fetch 脚本产物和规则文件...")
    leaderboard_data = read_json(leaderboard_current_path)
    leaderboard_rows = leaderboard_data.get("leaderboard") or []
    current_total = len(leaderboard_rows)
    logger.info("  current 榜单模型数: %d", current_total)
    logger.info("  榜单生成时间: %s", leaderboard_data.get("generated_at"))
    logger.info("  overrides_china_prefixes: %d", len(china_prefixes))
    logger.info("  overrides_model_size: %d", len(overrides_model_size))
    logger.info("  overrides_is_open_weight: %d", len(overrides_is_open_weight))

    # ── Step 2: 构建模型清单（raw pass） ─────────────────────────────────────
    logger.info("[2/5] 读取 submission 详情并按 submission 级有效性聚合...")
    raw_rows: list[dict] = []
    canonical_set: set[str] = set(canonical_override)
    selected_versions_set: set[str] = set(selected_versions)
    total_valid_subs = 0
    total_invalid_subs = 0

    for i, entry in enumerate(leaderboard_rows):
        submission_id = str(entry.get("best_submission_id") or "").strip()
        model_id = str(entry.get("model") or "")
        provider = str(entry.get("provider") or "")
        model_prefix = _model_prefix(model_id)

        # 从 best_submission_cache 读取 submission 详情
        detail_data = cache.get_submission_detail(submission_id)
        if detail_data is None:
            # Step 1 只保存了官方模型，非官方模型无缓存，跳过
            continue
        submission = detail_data.get("submission") or {}

        weights_raw = str(submission.get("weights") or "").strip() or None
        hf_link_raw = str(submission.get("hf_link") or "").strip() or None
        is_official = submission.get("official") is True
        is_china = _starts_with_any(model_id, china_prefixes)
        china_reason = "override" if is_china else None
        # 严格只看 overrides——未命中即闭源 / 参数量未知
        is_open = model_id in overrides_is_open_weight
        open_reason = "override" if is_open else None
        model_size_raw, model_size_b = _resolve_model_size(
            model_id,
            overrides_model_size,
        )

        # 该模型 submission 级有效性聚合
        submission_total: Optional[int] = None
        returned_count: Optional[int] = None
        valid_submission_ids: list[str] = []      # 顺序保留：用于 step3 重新读 detail 时复用
        invalid_reasons: dict[str, int] = {r: 0 for r in _INVALID_REASONS_ORDERED}
        sample_per_reason: dict[str, list[dict]] = {r: [] for r in _INVALID_REASONS_ORDERED}

        if is_official:
            # 读取该模型全部 submissions 列表（仅 step1 缓存；缺失即报错）
            submission_list = cache.get_submission_list(model_id, provider)
            if submission_list is None:
                raise FileNotFoundError(
                    f"缺少 submission list 缓存（{provider}/{model_id}）：请重新运行 `pinchbench-upgraded fetch`"
                )

            submission_total = int(submission_list.get("total") or 0)
            returned_count = int(submission_list.get("returned_count") or 0)

            for sub_summary in submission_list.get("submissions") or []:
                sub_id = str(sub_summary.get("id") or "")
                run_detail = cache.get_submission_detail(sub_id)
                if run_detail is None:
                    raise FileNotFoundError(
                        f"缺少 submission detail 缓存（{sub_id}）：请重新运行 `pinchbench-upgraded fetch`"
                    )

                run_sub = run_detail.get("submission") or {}
                # 前置版本过滤：不属于选定版本的 submission 既不计入 valid 也不计入 invalid_reasons
                sub_version = run_sub.get("benchmark_version")
                if sub_version not in selected_versions_set:
                    continue
                is_valid, reason, missing_tasks, extra_tasks = _classify_submission(
                    run_sub, canonical_set,
                )
                if is_valid:
                    valid_submission_ids.append(sub_id)
                else:
                    invalid_reasons[reason] += 1  # type: ignore[index]
                    # 每原因码留 2 份样本供 HTML 显示
                    if len(sample_per_reason[reason]) < 2:  # type: ignore[index]
                        sample: dict = {"submission_id": sub_id, "reason": reason}
                        _add_task_diag(sample, "missing_tasks", missing_tasks)
                        _add_task_diag(sample, "extra_tasks", extra_tasks)
                        sample_per_reason[reason].append(sample)  # type: ignore[index]

            total_valid_subs += len(valid_submission_ids)
            total_invalid_subs += sum(invalid_reasons.values())

        progress = round((i + 1) / current_total * 100, 1)
        logger.info("  [%d/%d] (%.1f%%) %s -> valid=%d invalid=%d",
                    i + 1, current_total, progress, model_id,
                    len(valid_submission_ids), sum(invalid_reasons.values()))

        # 把每原因码的 sample 平铺到一个 list（按 _INVALID_REASONS_ORDERED 顺序）
        sample_invalid_submissions: list[dict] = []
        if is_official:
            for reason in _INVALID_REASONS_ORDERED:
                sample_invalid_submissions.extend(sample_per_reason[reason])

        raw_rows.append({
            "model": model_id,
            "model_prefix": model_prefix,
            "provider": provider,
            "leaderboard_rank": i + 1,
            "best_score_percentage": round(float(entry.get("best_score_percentage") or 0) * 100, 2),
            "leaderboard_submission_count": entry.get("submission_count"),
            "submissions_total": submission_total,
            "returned_submission_count": returned_count,
            "latest_submission": entry.get("latest_submission"),
            "best_submission_id": submission_id,
            "benchmark_version": submission.get("benchmark_version"),
            "official": is_official,
            "weights": weights_raw,
            "hf_link": hf_link_raw,
            "model_size_raw": model_size_raw,
            "model_size_b": model_size_b,
            "is_china_model": is_china,
            "china_reason": china_reason,
            "is_open_weight_model": is_open,
            "open_weight_reason": open_reason,
            # 核心新字段
            "valid_submission_count": len(valid_submission_ids),
            "valid_submission_ids": valid_submission_ids,
            "invalid_reasons": invalid_reasons,
            "sample_invalid_submissions": sample_invalid_submissions,
        })

    total_subs = total_valid_subs + total_invalid_subs
    if total_subs > 0:
        logger.info(
            "  submission 级有效性判定：%d/%d 通过（失效 %d 条）",
            total_valid_subs, total_subs, total_invalid_subs,
        )
    else:
        logger.info("  submission 级有效性判定：无 submission（可能没有官方模型）")

    # ── Step 3: 汇总 ─────────────────────────────────────────────────────────
    logger.info("[3/5] 汇总统计...")

    canonical_task_ids: list[str] = sorted(set(canonical_override))
    logger.info("  规范任务全集（人工指定）: %d 个任务", len(canonical_task_ids))

    inventory: list[dict] = []
    for row in sorted(raw_rows, key=lambda r: r["leaderboard_rank"]):
        inventory.append({
            "model": row["model"],
            "model_prefix": row["model_prefix"],
            "provider": row["provider"],
            "leaderboard_rank": row["leaderboard_rank"],
            "best_score_percentage": row["best_score_percentage"],
            "leaderboard_submission_count": row["leaderboard_submission_count"],
            "submissions_total": row["submissions_total"],
            "returned_submission_count": row["returned_submission_count"],
            "latest_submission": row["latest_submission"],
            "best_submission_id": row["best_submission_id"],
            "benchmark_version": row["benchmark_version"],
            "official": row["official"],
            "weights": row["weights"],
            "hf_link": row["hf_link"],
            "model_size_raw": row["model_size_raw"],
            "model_size_b": row["model_size_b"],
            "is_china_model": row["is_china_model"],
            "china_reason": row["china_reason"],
            "is_open_weight_model": row["is_open_weight_model"],
            "open_weight_reason": row["open_weight_reason"],
            # 核心字段
            "valid_submission_count": row["valid_submission_count"],
            "valid_submission_ids": row["valid_submission_ids"],
            "invalid_reasons": row["invalid_reasons"],
            "sample_invalid_submissions": row["sample_invalid_submissions"],
        })

    official_rows = [r for r in inventory if r["official"]]
    unofficial_rows = [r for r in inventory if not r["official"]]
    # 「筛除模型」= 全部 submission 失效的官方模型
    filtered_out_rows = [r for r in official_rows if r["valid_submission_count"] == 0]
    ranking_rows = [r for r in official_rows if r["valid_submission_count"] > 0]

    logger.info("  current 总模型数: %d", current_total)
    logger.info("  官方模型数: %d", len(official_rows))
    logger.info("  非官方模型数: %d", len(unofficial_rows))
    logger.info("  进入排行榜（valid_submission_count > 0）: %d", len(ranking_rows))
    logger.info("  筛除模型（全部 submission 失效）: %d", len(filtered_out_rows))
    for fr in filtered_out_rows[:10]:
        primary_reasons = sorted(
            ((k, v) for k, v in fr["invalid_reasons"].items() if v > 0),
            key=lambda kv: -kv[1],
        )
        reason_str = ", ".join(f"{k}={v}" for k, v in primary_reasons[:3])
        logger.info("    - %s | %d 失效 | 主因: %s",
                    fr["model"], sum(fr["invalid_reasons"].values()), reason_str)

    # ── Step 4: 自动重生 candidates_*（overrides_* / selected_* 保持不变）──────
    logger.info("[4/5] 自动重生 candidates_*（overrides / selected 不修改）...")
    observed_prefixes = sorted({r["model_prefix"] for r in official_rows if r["model_prefix"]})
    overrides_prefixes_set = set(china_prefixes)
    candidates_china_prefixes = [
        {
            "prefix": p,
            "official_models": sorted(r["model"] for r in official_rows if r["model_prefix"] == p),
            "review_reason": "with manual review",
        }
        for p in observed_prefixes
        if p not in overrides_prefixes_set
    ]

    # candidates_model_size：选中版本下所有非 overrides 模型 + 自动检测建议值（None 也保留）
    candidates_model_size = [
        {
            "model": r["model"],
            "provider": r["provider"],
            "suggested_model_size_raw": detected_raw,
            "suggested_model_size_b": detected_size_b,
            "detected_from": detected_from,
            "review_reason": "with manual review",
        }
        for r in sorted(official_rows, key=lambda item: (item["model"], item["provider"]))
        if r["model"] not in overrides_model_size
        for detected_raw, detected_size_b, detected_from in [
            _detect_model_size(r["model"], r.get("hf_link"))
        ]
    ]

    # candidates_is_open_weight：选中版本下所有非 overrides 模型 + 上游 weights/hf_link 实录
    candidates_is_open_weight = [
        {
            "model": r["model"],
            "provider": r["provider"],
            "upstream_weights": r["weights"],
            "upstream_hf_link": r["hf_link"],
            "review_reason": "with manual review",
        }
        for r in sorted(official_rows, key=lambda item: (item["model"], item["provider"]))
        if r["model"] not in overrides_is_open_weight
    ]

    # ── 扫 step1 detail（按 selected_versions 过滤），得 task → (name_en, category_lower) 三元组
    observed_tasks: dict[str, tuple[str, str]] = _scan_step1_task_catalog(
        submissions_current_dir, selected_versions_set
    )
    logger.info("  扫描 step1 缓存得到唯一 task_id: %d", len(observed_tasks))

    # candidates_task_zh：观测到非 overrides_task_zh 的 task_id
    existing_task_zh_raw = raw_rules.get("overrides_task_zh") or {}
    existing_task_zh_keys = (
        {str(k).strip() for k in existing_task_zh_raw.keys() if str(k).strip()}
        if isinstance(existing_task_zh_raw, dict) else set()
    )
    candidates_task_zh = [
        {"task_id": tid, "task_name_en": name_en, "category_en": cat_en}
        for tid, (name_en, cat_en) in sorted(observed_tasks.items())
        if tid not in existing_task_zh_keys
    ]

    # candidates_category_zh：观测到非 overrides_category_zh 的 category（含 'uncategorized'）
    existing_cat_zh_raw = raw_rules.get("overrides_category_zh") or {}
    existing_cat_zh_keys = (
        {str(k).strip().lower() for k in existing_cat_zh_raw.keys() if str(k).strip()}
        if isinstance(existing_cat_zh_raw, dict) else set()
    )
    cat_to_sample_tids: dict[str, list[str]] = {}
    for tid, (_name, cat_en) in observed_tasks.items():
        cat_to_sample_tids.setdefault(cat_en, []).append(tid)
    candidates_category_zh = [
        {"category_en": cat_en, "sample_task_ids": sorted(tids)[:3]}
        for cat_en, tids in sorted(cat_to_sample_tids.items())
        if cat_en not in existing_cat_zh_keys
    ]

    # 写回：overrides_* / selected_* 严格保留原值，只重写 candidates_*
    notes_val = raw_rules.get("notes")
    existing_notes = notes_val if isinstance(notes_val, dict) else {}
    updated_rules = dict(raw_rules)
    updated_rules["candidates_china_prefixes"] = candidates_china_prefixes
    updated_rules["candidates_model_size"] = candidates_model_size
    updated_rules["candidates_is_open_weight"] = candidates_is_open_weight
    updated_rules["candidates_task_zh"] = candidates_task_zh
    updated_rules["candidates_category_zh"] = candidates_category_zh
    # 删除旧 schema 字段（如果存在）以避免噪声
    updated_rules.pop("category_mappings", None)
    cleaned_notes = {k: v for k, v in existing_notes.items() if k != "category_mappings"}
    updated_rules["notes"] = {**cleaned_notes, **_RULES_NOTES}
    write_json(rules_path, updated_rules)
    logger.info("  overrides_china_prefixes: %d (人工维护)", len(china_prefixes))
    logger.info("  candidates_china_prefixes: %d", len(candidates_china_prefixes))
    logger.info("  overrides_model_size: %d (人工维护)", len(overrides_model_size))
    logger.info("  candidates_model_size: %d", len(candidates_model_size))
    logger.info("  overrides_is_open_weight: %d (人工维护)", len(overrides_is_open_weight))
    logger.info("  candidates_is_open_weight: %d", len(candidates_is_open_weight))
    logger.info("  candidates_task_zh: %d", len(candidates_task_zh))
    logger.info("  candidates_category_zh: %d", len(candidates_category_zh))

    # ── Step 5: 写出结果 ──────────────────────────────────────────────────────
    logger.info("[5/5] 写出结果文件...")

    # 汇总各原因码总数（跨所有官方模型）
    aggregate_invalid_reasons: dict[str, int] = {r: 0 for r in _INVALID_REASONS_ORDERED}
    for r in official_rows:
        for code, cnt in r["invalid_reasons"].items():
            aggregate_invalid_reasons[code] = aggregate_invalid_reasons.get(code, 0) + cnt

    filtered_out_models = [
        {
            "model": fr["model"],
            "provider": fr["provider"],
            "invalid_reasons": fr["invalid_reasons"],
            "primary_reason": max(
                ((k, v) for k, v in fr["invalid_reasons"].items() if v > 0),
                key=lambda kv: kv[1],
                default=(None, 0),
            )[0],
        }
        for fr in filtered_out_rows
    ]

    summary = {
        "generated_at": leaderboard_data.get("generated_at"),
        "canonical_task_ids": canonical_task_ids,
        "canonical_task_count": len(canonical_task_ids),
        "current_total_models": current_total,
        "official_models": len(official_rows),
        "unofficial_models": len(unofficial_rows),
        "ranking_model_count": len(ranking_rows),
        "filtered_out_count": len(filtered_out_rows),
        "filtered_out_models": filtered_out_models,
        "aggregate_invalid_reasons": aggregate_invalid_reasons,
        "total_valid_submissions": total_valid_subs,
        "total_invalid_submissions": total_invalid_subs,
        "rules_file": str(rules_path),
        "overrides_china_prefix_count": len(china_prefixes),
        "candidates_china_prefix_count": len(candidates_china_prefixes),
        "overrides_model_size_count": len(overrides_model_size),
        "candidates_model_size_count": len(candidates_model_size),
        "rules_file_existed_before_run": rules_existed_before_run,
        "official_definition": "使用 submission.official 字段",
        "canonical_source": "manual_override",
        "selected_benchmark_versions": selected_versions,
        "selected_task_ids_count": len(canonical_override),
        "submission_validity_definition": (
            "二元有效性：仅处理 benchmark_version ∈ selected_benchmark_versions 的 submission（前置过滤，不计入失效统计）。"
            "一份选定版本下的 submission 视为有效 ⟺ 同时满足 "
            "(1) set(submission.tasks[*].task_id) == selected_task_ids（集合相等）、"
            "(2) usage_summary.total_cost_usd > 0、"
            "(3) 所有 task 的 execution_time_seconds > 0。"
            "失效按优先级单一归类：canonical_extra > canonical_missing > task_time_zero > cost_zero。"
            "valid_submission_count = 0 的官方模型进入「筛除模型」section，不参与排行榜。"
        ),
        "open_weight_definition": (
            "严格 overrides-only：model 在 overrides_is_open_weight 中 → open；否则 → closed。"
            "上游 weights / hf_link 仅作为 candidates_is_open_weight 的实录字段，不参与分类。"
        ),
        "china_definition": (
            "严格 overrides-only：model_prefix 在 overrides_china_prefixes 中 → 中国厂商；否则 → 非中国。"
        ),
        "model_size_definition": (
            "严格 overrides-only：model 在 overrides_model_size 中 → 用该条 model_size_raw/b；否则 → None（HTML 显示 -）。"
            "自动检测仅作为 candidates_model_size 的建议值（suggested_*），不参与分类。"
        ),
        "depends_on": [
            "leaderboard_current.json",
            "submissions/current/*.json",
            "current_model_scope_rules.json",
            "live submissions API",
            "live submission detail API",
        ],
    }

    inventory_path = scope_dir / "current_model_inventory.json"
    all_official_path = scope_dir / "current_all_official_models.json"
    summary_path = scope_dir / "current_model_scope_summary.json"

    write_json(inventory_path, sorted(inventory, key=lambda r: r["leaderboard_rank"]))
    write_json(all_official_path, sorted(official_rows, key=lambda r: r["leaderboard_rank"]))
    write_json(summary_path, summary)

    logger.info("输出文件:")
    logger.info("  %s", rules_path)
    logger.info("  %s", inventory_path)
    logger.info("  %s", all_official_path)
    logger.info("  %s", summary_path)
