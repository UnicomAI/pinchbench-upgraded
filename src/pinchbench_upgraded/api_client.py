"""统一 HTTP 客户端，替代 4 个脚本中分散的 Invoke-RestMethod。"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from pinchbench_upgraded.config import BASE_URL, LEADERBOARD_LIMIT, SUBMISSIONS_LIMIT


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exc, httpx.TransportError):
        return True
    return False


class PinchBenchClient:
    def __init__(
        self,
        delay_ms: int = 150,
        timeout: float = 60.0,
    ) -> None:
        self._delay_ms = delay_ms
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PinchBenchClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _sleep(self) -> None:
        if self._delay_ms > 0:
            time.sleep(self._delay_ms / 1000.0)

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    # ── 公共方法 ──────────────────────────────────────────────────────────────

    def get_leaderboard(
        self,
        benchmark_version: Optional[str] = None,
        official_only: bool = True,
    ) -> dict:
        params: dict = {"limit": LEADERBOARD_LIMIT}
        if benchmark_version:
            params["benchmark_version"] = benchmark_version
        if official_only:
            params["official"] = "true"
        data = self._get("/leaderboard", params)
        self._sleep()
        return data

    def get_current_benchmark_version(self) -> str | None:
        """调用 /benchmark_versions/latest 获取当前版本 hash。"""
        try:
            data = self._get("/benchmark_versions/latest")
            self._sleep()
            return (data.get("version") or {}).get("id")
        except Exception:
            return None

    def get_submission_detail(self, submission_id: str) -> dict:
        data = self._get(f"/submissions/{submission_id}")
        self._sleep()
        return data

    def get_submissions_for_model(
        self,
        model: str,
        provider: str,
        benchmark_version: Optional[str] = None,
        official_only: bool = True,
    ) -> list[dict]:
        """分页拉取并去重，返回 submission summary 列表。

        - 默认在服务端用 ``official=true`` 过滤，避免同名 (model, provider) 下
          第三方普通 token 提交的非官方 submission 被拉到。
        - 默认 ``benchmark_version=None`` 即不传该参数，由上游 API 走
          ``resolveBenchmarkVersions`` 的 fallback 分支自动按 ``current=1``
          的版本集合聚合（与 ``/leaderboard`` 默认行为一致）。**不要**传字符串
          ``"current"``——它不是合法的 version id，上游会回退到不加版本过滤，
          导致返回**所有历史版本**的 submissions（污染 current 数据）。
        """
        all_submissions: list[dict] = []
        offset = 0
        while True:
            params: dict = {
                "model": model,
                "provider": provider,
                "limit": SUBMISSIONS_LIMIT,
                "offset": offset,
            }
            if benchmark_version:
                params["benchmark_version"] = benchmark_version
            if official_only:
                params["official"] = "true"
            data = self._get("/submissions", params)
            self._sleep()
            page = data.get("submissions") or []
            all_submissions.extend(page)
            if not data.get("has_more"):
                break
            offset += SUBMISSIONS_LIMIT

        # 去重（保留首次出现）
        seen: set[str] = set()
        deduped: list[dict] = []
        for s in all_submissions:
            sid = s.get("id", "")
            if sid not in seen:
                seen.add(sid)
                deduped.append(s)
        return deduped
