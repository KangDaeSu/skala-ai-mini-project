"""agent/resilience.py — 재시도 대상 판별, 시도 횟수, 시간 예산, 구조화된 실패, 서킷 브레이커."""
import asyncio
import time

import httpx
import pytest

from agent import resilience as R

REQ = httpx.Request("POST", "http://llm.test")


def _status_error(code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(str(code), request=REQ,
                                 response=httpx.Response(code, request=REQ, headers=headers))


@pytest.fixture(autouse=True)
def fast_policy(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_BASE_DELAY", "0.01")
    monkeypatch.setenv("LLM_RETRIES", "2")


@pytest.mark.parametrize("exc, expected", [
    (httpx.ReadTimeout("t", request=REQ), True),
    (httpx.ConnectError("c", request=REQ), True),
    (asyncio.TimeoutError(), True),
    (ConnectionError("mcp session closed"), True),
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


def test_gives_up_with_structured_error():
    """재시도를 다 쓰면 원래 예외 대신 원인이 구조화된 ExternalCallError."""
    calls = []

    def fn(timeout):
        calls.append(timeout)
        raise _status_error(503)

    with pytest.raises(R.ExternalCallError) as info:
        R.call_sync("route", fn)
    assert len(calls) == 3   # 첫 시도 + 재시도 2회
    error = info.value.error
    assert (error["stage"], error["kind"], error["retryable"], error["attempts"]) == \
        ("route", "http_5xx", True, 3)
    assert isinstance(info.value.__cause__, httpx.HTTPStatusError)   # 원래 예외는 원인으로 남는다


def test_client_errors_are_not_retried():
    calls = []

    def fn(timeout):
        calls.append(timeout)
        raise _status_error(400)

    with pytest.raises(R.ExternalCallError) as info:
        R.call_sync("route", fn)
    assert len(calls) == 1
    assert (info.value.error["kind"], info.value.error["retryable"]) == ("http_4xx", False)


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
    with pytest.raises(R.ExternalCallError) as info:
        R.call_sync("route", hang)
    assert time.monotonic() - started < 0.8
    assert info.value.error["kind"] == "timeout"
    assert timeouts[0] == pytest.approx(0.3)
    assert all(t <= 0.3 for t in timeouts[1:])   # 두 번째 시도는 남은 예산만큼만 기다린다


def test_retry_after_header_is_honored(monkeypatch):
    """429가 Retry-After를 주면 백오프 대신 그 시간을 기다린다."""
    slept = []
    monkeypatch.setattr(R.time, "sleep", lambda s: slept.append(s))
    calls = []

    def fn(timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise _status_error(429, {"retry-after": "1.5"})
        return "ok"

    assert R.call_sync("write", fn) == ("ok", 1)
    assert slept == [1.5]


def test_backoff_has_jitter(monkeypatch):
    monkeypatch.setenv("LLM_RETRY_BASE_DELAY", "1.0")
    monkeypatch.setenv("LLM_RETRIES", "1")
    slept = []
    monkeypatch.setattr(R.time, "sleep", lambda s: slept.append(s))
    calls = []

    def fn(timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise _status_error(503)
        return "ok"

    R.call_sync("write", fn)
    assert 0.8 <= slept[0] <= 1.2


def test_permanent_error_is_not_retried_async():
    calls = []

    async def fn(timeout):
        calls.append(timeout)
        raise R.PermanentError("스트리밍 도중 실패")

    with pytest.raises(R.ExternalCallError) as info:
        asyncio.run(R.call_async("write", fn))
    assert len(calls) == 1
    assert info.value.error["kind"] == "partial_stream"


def test_circuit_opens_after_consecutive_outages_and_recovers(monkeypatch):
    """같은 서비스가 연속 3회 실패하면 cooldown 동안 호출 없이 즉시 실패, 지나면 다시 시도."""
    monkeypatch.setenv("LLM_RETRIES", "0")
    monkeypatch.setenv("CIRCUIT_COOLDOWN", "0.3")
    calls = []

    def down(timeout):
        calls.append(timeout)
        raise _status_error(503)

    for _ in range(3):
        with pytest.raises(R.ExternalCallError):
            R.call_sync("plan", down)
    with pytest.raises(R.ExternalCallError) as info:
        R.call_sync("route", down)   # route도 같은 "llm" 서비스 — 차단된다
    assert info.value.error["kind"] == "circuit_open"
    assert len(calls) == 3            # 차단 중에는 호출하지 않았다

    time.sleep(0.35)                  # cooldown이 지나면 한 번 시도해 보고, 성공하면 닫힌다
    assert R.call_sync("route", lambda t: "ok") == ("ok", 0)
    assert R.breaker_for("route").failures == 0


def test_client_errors_do_not_open_the_circuit(monkeypatch):
    """4xx는 우리 요청의 문제이지 서비스 장애가 아니다 — 차단 횟수에 세지 않는다."""
    monkeypatch.setenv("LLM_RETRIES", "0")
    for _ in range(5):
        with pytest.raises(R.ExternalCallError):
            R.call_sync("plan", lambda t: (_ for _ in ()).throw(_status_error(400)))
    assert R.call_sync("plan", lambda t: "ok") == ("ok", 0)


def test_guard_structures_external_failures_but_not_bugs():
    def external(*args):
        raise R.ExternalCallError({"stage": "plan", "kind": "timeout", "retryable": True,
                                   "attempts": 3, "elapsed_s": 1.0, "message": "t"})

    result = asyncio.run(R.guard(external))
    assert (result.ok, result.error["kind"]) == (False, "timeout")
    assert asyncio.run(R.guard(lambda x: x * 2, 21)).value == 42

    def bug(*args):
        raise KeyError("우리 코드의 버그")

    with pytest.raises(KeyError):   # 버그는 폴백 뒤에 숨기지 않는다
        asyncio.run(R.guard(bug))


def test_env_overrides_policy(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_WRITE", "12")
    monkeypatch.setenv("LLM_MAX_TOKENS_JSON", "64")
    assert R.policy_for("write").timeout == 12
    assert R.max_tokens(json_output=True) == 64
