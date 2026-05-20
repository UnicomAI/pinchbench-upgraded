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
_env.filters["beijing"] = _to_beijing
_env.filters["beijing_en"] = _to_beijing_en


def render_task_rankings(data: dict) -> str:
    tmpl = _env.get_template("task_rankings.html")
    return tmpl.render(**data)


def render_category_rankings(data: dict) -> str:
    tmpl = _env.get_template("category_rankings.html")
    return tmpl.render(**data)
