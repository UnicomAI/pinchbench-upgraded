"""Step 1: 抓取 leaderboard + 全量 submissions（list + 每条 detail）。"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from pinchbench_upgraded.api_client import PinchBenchClient
from pinchbench_upgraded.config import FETCH_DELAY_MS, safe_filename
from pinchbench_upgraded.utils import read_json, write_json

logger = logging.getLogger(__name__)


def _build_versioned_dir_name(
    is_current: bool,
    version_hash: str,
) -> str:
    """构造版本化文件夹名。

    - current 版本: current-newest{hash}-{YYYYMMDD}
    - 指定版本:     {hash}-{YYYYMMDD}
    """
    today = date.today().strftime("%Y%m%d")
    if is_current:
        return f"current-newest{version_hash}-{today}"
    return f"{version_hash}-{today}"


def run(
    data_dir: Path,
    benchmark_version: Optional[str] = None,
    force_refresh: bool = False,
) -> Path:
    """执行 Step 1 数据拉取（leaderboard + 每模型全量 submissions）。

    Returns:
        版本化输出目录的路径（data_dir 下的子目录）。
    """
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("PinchBench-Upgraded 数据批量拉取")
    logger.info("=" * 60)

    normalized_version = benchmark_version.strip() if benchmark_version else None
    safe_version = safe_filename(normalized_version) if normalized_version else None
    is_current = normalized_version is None

    with PinchBenchClient(delay_ms=FETCH_DELAY_MS) as client:
        # ── 1. 拉取 current 榜单 ──────────────────────────────────────────────
        logger.info("[1/5] 拉取排行榜与版本列表...")
        leaderboard_current = client.get_leaderboard()

        current_entries = leaderboard_current.get("leaderboard") or []
        versions = [
            str(v).strip()
            for v in (leaderboard_current.get("benchmark_versions") or [])
            if v and str(v).strip()
        ]

        # ── 2. 确定版本 hash，构造版本化输出目录 ─────────────────────────────
        if is_current:
            logger.info("[2/5] 确定 current 版本 hash...")
            version_hash = client.get_current_benchmark_version()
            if version_hash:
                logger.info("  /benchmark_versions/latest 返回: %s", version_hash)
            elif versions:
                version_hash = versions[0]
                logger.info("  回退使用 benchmark_versions[0]: %s", version_hash)
            else:
                version_hash = "unknown"
                logger.warning("  无法确定版本 hash，使用 'unknown'")
        else:
            logger.info("[2/5] 使用指定版本: %s", normalized_version)
            version_hash = safe_version or normalized_version

        dir_name = _build_versioned_dir_name(is_current, version_hash)
        versioned_dir = data_dir / dir_name
        versioned_dir.mkdir(parents=True, exist_ok=True)
        submissions_root = versioned_dir / "submissions"
        submissions_root.mkdir(exist_ok=True)
        logger.info("  输出目录: %s", versioned_dir)
        if force_refresh:
            logger.info("  --force-refresh 已启用：将忽略本地缓存重新拉取")

        # ── 保存 leaderboard 和版本清单 ──────────────────────────────────────
        leaderboard_current_path = versioned_dir / "leaderboard_current.json"
        write_json(leaderboard_current_path, leaderboard_current)
        logger.info("  默认接口返回 current 榜单视图，共 %d 个模型", len(current_entries))
        logger.info("  已保存 current 榜单: %s", leaderboard_current_path)

        version_manifest = {
            "fetched_at": leaderboard_current.get("generated_at"),
            "benchmark_versions": versions,
            "note": (
                "这些 benchmark_version 是 pinchbench/skill 仓库的 commit hash。"
                "默认 leaderboard 接口返回 current 视图；指定 benchmark_version 可查看某个历史快照。"
            ),
        }
        benchmark_versions_path = versioned_dir / "benchmark_versions.json"
        write_json(benchmark_versions_path, version_manifest)
        if versions:
            logger.info("  可用 benchmark_versions: %s", ", ".join(versions))
        else:
            logger.warning("  API 未返回 benchmark_versions")
        logger.info("  已保存版本列表: %s", benchmark_versions_path)

        # ── 决定本次详情拉取使用哪个榜单 ─────────────────────────────────────
        leaderboard = leaderboard_current
        leaderboard_label = "current 榜单"
        target_tag = "current"
        list_target_tag = "current_lists"

        if normalized_version:
            if versions and normalized_version not in versions:
                logger.warning("  警告: 指定版本 [%s] 不在版本列表中，仍将尝试请求", normalized_version)
            logger.info("  额外拉取指定版本 [%s]...", normalized_version)
            try:
                leaderboard_selected = client.get_leaderboard(benchmark_version=normalized_version)
                selected_path = versioned_dir / f"leaderboard_version_{safe_version}.json"
                write_json(selected_path, leaderboard_selected)
                sel_entries = leaderboard_selected.get("leaderboard") or []
                logger.info("  成功! 该版本下有 %d 个模型", len(sel_entries))
                logger.info("  已保存指定版本榜单: %s", selected_path)
                leaderboard = leaderboard_selected
                leaderboard_label = f"benchmark_version={normalized_version}"
                target_tag = f"version_{safe_version}"
                list_target_tag = f"version_{safe_version}_lists"
            except Exception as exc:
                logger.error("  指定版本拉取失败，改用 current 榜单继续: %s", exc)

        detail_output_dir = submissions_root / target_tag
        detail_output_dir.mkdir(exist_ok=True)
        lists_output_dir = submissions_root / list_target_tag
        lists_output_dir.mkdir(exist_ok=True)

        # ── 3. 准备清单 ───────────────────────────────────────────────────────
        models = leaderboard.get("leaderboard") or []
        total_models = len(models)
        logger.info("[3/5] 准备详情拉取清单...")
        logger.info("  数据来源: %s", leaderboard_label)
        logger.info("  共 %d 个模型需要拉取全量 submissions", total_models)

        # ── 4. 拉每模型 submissions list ──────────────────────────────────────
        logger.info("[4/5] 拉取每个模型的 submissions 列表 (%d 个模型)...", total_models)
        logger.info("  list 输出目录: %s", lists_output_dir)

        # 收集 (model, provider, list_payload) 用于第 5 步详情拉取
        per_model_lists: list[dict] = []
        list_fetched = 0
        list_cached = 0
        list_failed = 0
        # benchmark_version=None 表示不传该参数，由上游按 current=1 集合聚合。
        # 显式传字符串 "current" 在上游会被识别为非法 version id 而退化为"返回全部历史版本"，
        # 详见 api_client.get_submissions_for_model 的 docstring。
        list_query_version: Optional[str] = normalized_version  # 仅在 --benchmark-version 指定时传
        list_query_label = list_query_version or "current（按服务端 current=1 集合聚合）"

        for i, m in enumerate(models):
            model_name = str(m.get("model") or "")
            provider_name = str(m.get("provider") or "") or "unknown_provider"
            safe_p = safe_filename(provider_name)
            safe_m = safe_filename(model_name)
            list_file = lists_output_dir / f"{safe_p}__{safe_m}.json"

            progress = round((i + 1) / total_models * 100, 1)

            if list_file.exists() and not force_refresh:
                payload = read_json(list_file)
                sub_summaries = payload.get("submissions") or []
                logger.info(
                    "  [%d/%d] (%.1f%%) %s ... list cached (%d submissions)",
                    i + 1, total_models, progress, model_name, len(sub_summaries),
                )
                list_cached += 1
            else:
                logger.info(
                    "  [%d/%d] (%.1f%%) %s ... fetching list",
                    i + 1, total_models, progress, model_name,
                )
                try:
                    sub_summaries = client.get_submissions_for_model(
                        model_name,
                        provider_name,
                        benchmark_version=list_query_version,
                        official_only=True,
                    )
                    payload = {
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "model": model_name,
                        "provider": provider_name,
                        "benchmark_version_query": list_query_label,
                        "total": len(sub_summaries),
                        "returned_count": len(sub_summaries),
                        "submissions": sub_summaries,
                    }
                    write_json(list_file, payload)
                    logger.info("    OK (%d submissions)", len(sub_summaries))
                    list_fetched += 1
                except Exception as exc:
                    logger.error("    FAILED: %s", exc)
                    list_failed += 1
                    continue

            per_model_lists.append({
                "model": model_name,
                "provider": provider_name,
                "safe_p": safe_p,
                "safe_m": safe_m,
                "submissions": sub_summaries,
            })

        # ── 5. 拉每条 submission 的 detail ────────────────────────────────────
        total_details = sum(len(entry["submissions"]) for entry in per_model_lists)
        logger.info("[5/5] 拉取每条 submission 详情（合计 %d 条）...", total_details)
        logger.info("  detail 输出目录: %s", detail_output_dir)
        logger.info("  每次请求间隔 %.1f 秒", FETCH_DELAY_MS / 1000.0)

        detail_fetched = 0
        detail_cached = 0
        detail_failed = 0
        failed_details: list[tuple[str, str, str]] = []
        seen_global = 0

        for entry in per_model_lists:
            model_name = entry["model"]
            safe_p = entry["safe_p"]
            safe_m = entry["safe_m"]
            sub_list = entry["submissions"]

            for sub_summary in sub_list:
                seen_global += 1
                sub_id = str(sub_summary.get("id") or "").strip()
                if not sub_id:
                    detail_failed += 1
                    failed_details.append((model_name, "(missing-id)", "submission id 为空"))
                    logger.error("  [%d/%d] %s missing id", seen_global, total_details, model_name)
                    continue

                out_file = detail_output_dir / f"{safe_p}__{safe_m}__{sub_id}.json"
                progress = round(seen_global / total_details * 100, 1) if total_details else 100.0

                if out_file.exists() and not force_refresh:
                    detail_cached += 1
                    continue

                try:
                    detail = client.get_submission_detail(sub_id)
                    write_json(out_file, detail)
                    detail_fetched += 1
                    if detail_fetched % 25 == 0:
                        logger.info(
                            "  [%d/%d] (%.1f%%) fetched %s/%s",
                            seen_global, total_details, progress, model_name, sub_id,
                        )
                except Exception as exc:
                    detail_failed += 1
                    failed_details.append((model_name, sub_id, str(exc)))
                    logger.error(
                        "  [%d/%d] %s/%s FAILED: %s",
                        seen_global, total_details, model_name, sub_id, exc,
                    )

    # ── 汇总 ──────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("拉取完成!")
    logger.info("=" * 60)
    logger.info("  数据来源: %s", leaderboard_label)
    logger.info("  list  -> fetched=%d  cached=%d  failed=%d", list_fetched, list_cached, list_failed)
    logger.info("  detail-> fetched=%d  cached=%d  failed=%d", detail_fetched, detail_cached, detail_failed)
    logger.info("  %s", benchmark_versions_path)
    logger.info("  %s", leaderboard_current_path)
    logger.info("  %s/*.json", lists_output_dir)
    logger.info("  %s/*.json", detail_output_dir)
    if failed_details:
        logger.error("  失败详情 (%d 条):", len(failed_details))
        for model_name, sid, err in failed_details[:20]:
            logger.error("    - %s/%s: %s", model_name, sid, err)
        if len(failed_details) > 20:
            logger.error("    ... 余下 %d 条略", len(failed_details) - 20)

    if list_failed or detail_failed:
        raise RuntimeError(
            f"Step 1 失败: list 失败 {list_failed} 个模型；detail 失败 {detail_failed} 条 submission。"
            f"请检查日志后重试（可加 --force-refresh）。"
        )

    return versioned_dir
