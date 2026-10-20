"""agent/resilience.py — 재시도 대상 판별, 시도 횟수, 시간 예산."""
import asyncio
import time

import httpx
import pytest

from agent import resilience as R

REQ = httpx.Request("POST", "http://llm.test")


def _status_error(code: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(str(code), request=REQ, response=httpx.Response(code, request=REQ))


@pytest.fixture(autouse=True)
def fast_policy(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_BASE_DELAY", "0.01")
    monkeypatch.setenv("LLM_RETRIES", "2")


@pytest.mark.parametrize("exc, expected", [
    (httpx.ReadTimeout("t", request=REQ), True),
    (httpx.ConnectError("c", request=REQ), True),
    (_status_error(503), True),
    (_status_error(429), True),
    (_status_error(400), False),
    (_status_error(401), False),
    (R.PermanentError("partial stream"), False),
    (ValueError("bug"), False),
])
def test_is_transient(exc, expected):
    assert R.is_transient(exc) is expected


def test_transient_errors_are_retried_until_success():
    calls = []

    def fn(timeout):
        calls.append(timeout)
        if len(calls) < 3:
            raise httpx.ReadTimeout("t", request=REQ)
        return "ok"

    result, retries = R.call_sync("route", fn)
    assert (result, retries) == ("ok", 2)
    assert len(calls) == 3


def test_gives_up_after_retries():
    calls = []

    def fn(timeout):
        calls.append(timeout)
        raise _status_error(503)

    with pytest.raises(httpx.HTTPStatusError):
        R.call_sync("route", fn)
    assert len(calls) == 3   # 첫 시도 + 재시도 2회


def test_client_errors_are_not_retried():
    calls = []

    def fn(timeout):
        calls.append(timeout)
        raise _status_error(400)

    with pytest.raises(httpx.HTTPStatusError):
        R.call_sync("route", fn)
    assert len(calls) == 1


def test_budget_caps_total_time(monkeypatch):
    """응답 없음이 계속돼도 전체 시간 예산 안에서 멈춘다 (baseline: 300초 대기)."""
    monkeypatch.setenv("LLM_TIMEOUT_ROUTE", "0.3")
    monkeypatch.setenv("LLM_BUDGET_ROUTE", "0.5")
    timeouts = []

    def hang(timeout):
        timeouts.append(timeout)
        time.sleep(timeout)
        raise httpx.ReadTimeout("hang", request=REQ)

    started = time.monotonic()
    with pytest.raises(httpx.ReadTimeout):
        R.call_sync("route", hang)
    assert time.monotonic() - started < 0.8
    assert timeouts[0] == pytest.approx(0.3)
    assert all(t <= 0.3 for t in timeouts[1:])   # 두 번째 시도는 남은 예산만큼만 기다린다


def test_permanent_error_is_not_retried_async():
    calls = []

    async def fn(timeout):
        calls.append(timeout)
        raise R.PermanentError("스트리밍 도중 실패")

    with pytest.raises(R.PermanentError):
        asyncio.run(R.call_async("write", fn))
    assert len(calls) == 1


def test_env_overrides_policy(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_WRITE", "12")
    monkeypatch.setenv("LLM_MAX_TOKENS_JSON", "64")
    assert R.policy_for("write").timeout == 12
    assert R.max_tokens(json_output=True) == 64
