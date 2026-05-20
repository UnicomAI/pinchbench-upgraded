"""argparse CLI 入口。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )


def _default_data_dir() -> Path:
    return Path(__file__).parent.parent.parent / "pinchbench_data"


def _default_rules_file() -> Path:
    return Path(__file__).parent.parent.parent / "current_model_scope_rules.json"


def _resolve_versioned_dir(data_dir: Path) -> Path:
    """读取 .active_version 标记文件，返回版本化输出目录。"""
    marker = data_dir / ".active_version"
    if not marker.exists():
        raise SystemExit(
            f"错误: 未找到 {marker}\n请先运行 fetch 以创建版本化输出目录。"
        )
    name = marker.read_text(encoding="utf-8").strip()
    vdir = data_dir / name
    if not vdir.is_dir():
        raise SystemExit(f"错误: 版本目录不存在: {vdir}")
    return vdir


def main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="pinchbench-upgraded",
        description="PinchBench-Upgraded 数据流水线（分步执行：fetch → inventory → scope → task-rankings → category-rankings）",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="输出目录（默认：<package-root>/pinchbench_data）",
    )
    parser.add_argument(
        "--rules-file",
        type=Path,
        default=None,
        help="规则文件路径（默认：<package-root>/current_model_scope_rules.json）",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── fetch ─────────────────────────────────────────────────────────────────
    sp_fetch = subparsers.add_parser(
        "fetch",
        help="Step 1: 抓取 leaderboard + 每模型全量 submissions（list + 每条 detail）",
    )
    sp_fetch.add_argument("--benchmark-version", default=None, help="指定历史版本 hash")
    sp_fetch.add_argument(
        "--force-refresh",
        action="store_true",
        help="忽略本地 list/detail 缓存，强制重新拉取",
    )

    # ── inventory ─────────────────────────────────────────────────────────────
    subparsers.add_parser(
        "inventory",
        help="Step 1.5: 生成版本盘点报告，为人工填写 selected_benchmark_versions 与 selected_task_ids 提供依据",
    )

    # ── scope ─────────────────────────────────────────────────────────────────
    subparsers.add_parser("scope", help="Step 2: 筛选模型范围")

    # ── task-rankings ─────────────────────────────────────────────────────────
    subparsers.add_parser("task-rankings", help="Step 3: 各规范任务排行榜")

    # ── category-rankings ─────────────────────────────────────────────────────
    subparsers.add_parser(
        "category-rankings",
        help="Step 4: 按上游 frontmatter.category 自动分组的大类排行榜",
    )

    args = parser.parse_args()

    data_dir: Path = args.data_dir or _default_data_dir()
    rules_file: Path = args.rules_file or _default_rules_file()

    cmd = args.command

    # ── fetch（step1）：创建版本化子目录并写入 .active_version ────────────────
    versioned_dir: Path | None = None
    if cmd == "fetch":
        from pinchbench_upgraded.steps import step1_fetch
        bv = getattr(args, "benchmark_version", None)
        fr = getattr(args, "force_refresh", False)
        versioned_dir = step1_fetch.run(data_dir, benchmark_version=bv, force_refresh=fr)
        # 记录活跃版本，供后续单独运行 step2-4 时使用
        (data_dir / ".active_version").write_text(
            versioned_dir.name, encoding="utf-8"
        )

    # ── step1.5/step2-4：使用版本化目录 ───────────────────────────────────────
    if cmd in ("inventory", "scope", "task-rankings", "category-rankings"):
        versioned_dir = _resolve_versioned_dir(data_dir)

    if cmd == "inventory":
        from pinchbench_upgraded.steps import step1_5_inventory
        step1_5_inventory.run(versioned_dir, rules_file)

    if cmd == "scope":
        from pinchbench_upgraded.steps import step2_model_scope
        step2_model_scope.run(versioned_dir, rules_file)

    if cmd == "task-rankings":
        from pinchbench_upgraded.steps import step3_task_rankings
        step3_task_rankings.run(versioned_dir, rules_file)

    if cmd == "category-rankings":
        from pinchbench_upgraded.steps import step4_category_rankings
        step4_category_rankings.run(versioned_dir, rules_file)


if __name__ == "__main__":
    main()
