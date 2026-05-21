"""Jinja2 渲染入口。"""

from __future__ import annotations

import base64
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pinchbench_upgraded.config import FILTER_DEFAULTS

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_LOGO_PATH = Path(__file__).parent / "logo.png"
_BJT = timezone(timedelta(hours=8))

# ── i18n 字典 ────────────────────────────────────────────────────────────────
# Single source of truth：server-side 后处理 data-i18n 元素 + JS 端主动切换语言均读取此字典。
# 模板里所有 `<TAG data-i18n="KEY">中文 fallback</TAG>` 在渲染后会被 _i18n_postprocess
# 按 FILTER_DEFAULTS["lang"] 替换为对应语言文本。
I18N_DICT: dict[str, dict[str, str]] = {
    "sidebar_title":        {"zh": "PinchBench-Upgraded · 排行榜",      "en": "PinchBench-Upgraded · Leaderboard"},
    "section_overview":     {"zh": "概览",                              "en": "Overview"},
    "page_title_task":      {"zh": "任务排行榜",                        "en": "Task Rankings"},
    "page_title_cat":       {"zh": "大类排行榜",                        "en": "Category Rankings"},
    "filter_obs":           {"zh": "运行次数阈值",                      "en": "Min Runs"},
    "filter_country":       {"zh": "国别",                              "en": "Country"},
    "filter_china":         {"zh": "中国",                              "en": "China"},
    "filter_other":         {"zh": "其他国家",                          "en": "Other"},
    "filter_all":           {"zh": "不限",                              "en": "All"},
    "filter_open_label":    {"zh": "开源",                              "en": "Source"},
    "filter_open":          {"zh": "开源",                              "en": "Open"},
    "filter_closed":        {"zh": "闭源",                              "en": "Closed"},
    "col_seq":              {"zh": "#",                                  "en": "#"},
    "col_attr":             {"zh": "属性",                              "en": "Attr."},
    "col_rank":             {"zh": "排名",                              "en": "Rank"},
    "col_model":            {"zh": "模型",                              "en": "Model"},
    "col_provider":         {"zh": "供应商",                            "en": "Provider"},
    "col_run_count":        {"zh": "运行次数",                          "en": "Runs"},
    "col_success_rate":     {"zh": "成功率 (%)",                        "en": "Success (%)"},
    "col_cost":             {"zh": "成本 ($)",                          "en": "Cost ($)"},
    "col_duration":         {"zh": "耗时 (s)",                          "en": "Duration (s)"},
    "col_duration_min":     {"zh": "耗时 (min)",                        "en": "Duration (min)"},
    "col_model_size":       {"zh": "参数量 (B)",                        "en": "Size (B)"},
    "col_value":            {"zh": "性价比 (%/USD)",                    "en": "Value (%/USD)"},
    "col_time_eff":         {"zh": "时效比 (%/s)",                      "en": "Time Eff. (%/s)"},
    "col_time_eff_min":     {"zh": "时效比 (%/min)",                    "en": "Time Eff. (%/min)"},
    "col_model_name":       {"zh": "模型",                              "en": "Model"},
    "tag_china_open":       {"zh": "中国 · 开源",                        "en": "China · Open"},
    "tag_china_closed":     {"zh": "中国 · 闭源",                        "en": "China · Closed"},
    "tag_other_open":       {"zh": "外国 · 开源",                        "en": "Other · Open"},
    "tag_other_closed":     {"zh": "外国 · 闭源",                        "en": "Other · Closed"},
    "col_total_subs":       {"zh": "提交记录总数",                      "en": "Total Submissions"},
    "col_valid_subs":       {"zh": "有效记录总数",                      "en": "Valid Submissions"},
    "col_canonical_extra":  {"zh": "任务数量过多",                      "en": "Extra Tasks"},
    "col_canonical_missing":{"zh": "任务数量过少",                      "en": "Missing Tasks"},
    "col_task_time_zero":   {"zh": "缺少时间统计",                      "en": "Missing Time"},
    "col_cost_zero":        {"zh": "缺少成本统计",                      "en": "Missing Cost"},
    "section_metrics":      {"zh": "指标说明",                          "en": "Metrics"},
    "section_models":       {"zh": "模型列表",                          "en": "Models"},
    "section_filtered_out": {"zh": "筛除模型归因",                      "en": "Filtered-out Attribution"},
    "section_catoverview":  {"zh": "大类与任务",                        "en": "Categories & Tasks"},
    "section_overall":      {"zh": "总排行榜",                          "en": "Overall Ranking"},
    "stat_benchmark":       {"zh": "PinchBench 版本",                   "en": "PinchBench Version"},
    "stat_models_card":     {"zh": "模型",                              "en": "Models"},
    "stat_submissions_card":{"zh": "提交记录",                          "en": "Submissions"},
    "stat_sub_official":    {"zh": "官方",                              "en": "Official"},
    "stat_sub_filtered":    {"zh": "筛除",                              "en": "Filtered"},
    "stat_sub_valid":       {"zh": "有效",                              "en": "Valid"},
    "stat_sub_total":       {"zh": "总数",                              "en": "Total"},
    "col_record_count":     {"zh": "记录总数",                          "en": "Submissions"},
    "tag_open_china":       {"zh": "开源 · 国产",                       "en": "Open · China"},
    "tag_open":             {"zh": "开源",                              "en": "Open Source"},
    "tag_china":            {"zh": "国产",                              "en": "China"},
    "task_label_category":  {"zh": "类别：",                            "en": "Category: "},
    "task_label_grading":   {"zh": "评分机制：",                        "en": "Grading: "},
    "task_label_models":    {"zh": "个模型",                            "en": " models"},
    "cat_label_scenarios":  {"zh": "个任务",                            "en": " tasks"},
    "sidebar_tasks":        {"zh": "任务列表",                          "en": "Tasks"},
    "sidebar_cats":         {"zh": "大类列表",                          "en": "Categories"},
}

# 匹配 `<TAG ... data-i18n="key" ...>纯文本</TAG>`：
# - 不允许嵌套：内文本不含 `<`
# - 闭合标签必须与开闭一致（反向引用 \2）
_DATA_I18N_RE = re.compile(
    r'(<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bdata-i18n="([^"]+)"[^>]*>)'
    r'([^<]*)'
    r'(</\2>)',
    re.DOTALL,
)


def _i18n_postprocess(html: str, lang: str) -> str:
    """渲染完成后，把模板里的 data-i18n 中文 fallback 文本替换为目标语言文本。

    模板里保留 `<TAG data-i18n="KEY">中文</TAG>` 的写法（中文 fallback 便于编辑期间看），
    后处理时根据 ``lang`` 从 :data:`I18N_DICT` 取出对应文本替换。字典里没有的 key 保持原样。
    """
    def repl(m: re.Match[str]) -> str:
        open_tag, _tag_name, key, _old_text, close_tag = m.groups()
        entry = I18N_DICT.get(key)
        if not entry or lang not in entry:
            return m.group(0)
        return f"{open_tag}{entry[lang]}{close_tag}"
    return _DATA_I18N_RE.sub(repl, html)


_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _fmt(value, decimals: int = 2) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{decimals}f}"


def _fmt_model_size(value) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    compound = re.fullmatch(r"(?i)(\d+(?:\.\d+)?)b-(a\d+(?:\.\d+)?)b", text)
    if compound:
        return f"{compound.group(1)}-{compound.group(2)}"
    if re.fullmatch(r"(?i)\d+(?:\.\d+)?b", text):
        return text[:-1]
    return text


def _load_logo_b64() -> str:
    """读取 logo PNG 并返回 base64 data URI。"""
    if _LOGO_PATH.exists():
        raw = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{raw}"
    return ""


def _to_beijing(ts_str: object) -> str:
    """将 ISO 时间戳转换为北京时间显示。"""
    if not ts_str:
        return "-"
    try:
        s = str(ts_str)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.astimezone(_BJT).strftime("%Y-%m-%d %H:%M:%S 北京时间")
    except Exception:
        return str(ts_str)


def _to_beijing_en(ts_str: object) -> str:
    """Convert ISO timestamp to Beijing time for English display (CST suffix)."""
    if not ts_str:
        return "-"
    try:
        s = str(ts_str)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.astimezone(_BJT).strftime("%Y-%m-%d %H:%M:%S CST")
    except Exception:
        return str(ts_str)


_env.globals["fmt"] = _fmt
_env.globals["fmt_model_size"] = _fmt_model_size
_env.globals["logo_src"] = _load_logo_b64()
_env.globals["filter_defaults"] = FILTER_DEFAULTS
_env.globals["I18N"] = I18N_DICT
_env.filters["beijing"] = _to_beijing
_env.filters["beijing_en"] = _to_beijing_en


def render_task_rankings(data: dict) -> str:
    tmpl = _env.get_template("task_rankings.html")
    html = tmpl.render(**data)
    return _i18n_postprocess(html, FILTER_DEFAULTS["lang"])


def render_category_rankings(data: dict) -> str:
    tmpl = _env.get_template("category_rankings.html")
    html = tmpl.render(**data)
    return _i18n_postprocess(html, FILTER_DEFAULTS["lang"])
