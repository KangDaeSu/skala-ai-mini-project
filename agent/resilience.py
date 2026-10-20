"""외부 호출 방어선 — LLM · MCP · 임베딩 호출의 타임아웃 · 재시도 · 시간 예산 · 서킷 브레이커,
그리고 실패를 구조화된 결과(ok / error)로 돌려주는 경계.

baseline은 LLM 호출 하나에 timeout 300초(Ollama)/120초(OpenAI)만 걸려 있고 재시도가 없어,
모델이 응답하지 않으면 그 시간을 통째로 기다린 뒤 예외가 그래프 밖으로 터졌다(실측: 302초 후
HTTP 500). MCP 호출은 재시도도 예외 처리도 없었다.

- 시도당 타임아웃: route 같은 짧은 분류와 write 같은 긴 생성의 정상 소요 시간이 다르므로 단계별로 둔다
- 재시도: 일시 오류(타임아웃·연결 실패·5xx·429)만 지수 백오프(+지터)로 재시도, 그 외는 즉시 포기.
  429/503이 Retry-After 헤더를 주면 그 시간을 따른다 (retry.py의 Wave 9 원칙을 확장)
- 전체 시간 예산: 재시도까지 합친 상한 — 남은 예산이 시도당 타임아웃보다 작으면 남은 만큼만 기다린다
- 서킷 브레이커: 같은 서비스(llm / mcp / embed)가 연속으로 실패하면 잠시 호출하지 않고 즉시 실패시켜,
  죽은 서비스에 요청마다 예산을 다 쓰지 않게 한다
- 요청 전체 deadline: 요청 하나가 쓸 수 있는 총시간(REQUEST_DEADLINE, 기본 60초). 단계별 예산이
  남아 있어도 요청 deadline을 넘기지 않고, 이미 넘겼으면 호출하지 않고 즉시 실패(kind=deadline) →
  남은 단계는 바로 폴백한다 (이전: 단계 예산이 합쳐져 LLM+MCP 장애 시 최대 115초)
- 실패의 구조화: 재시도를 다 쓴 실패는 원래 예외 대신 ExternalCallError(error={stage, kind, retryable,
  attempts, elapsed_s, message})로 던진다. 노드는 guard()로 감싸 CallResult(ok=True/False)로 받는다.
  ExternalCallError가 아닌 예외(우리 코드의 버그)는 guard가 잡지 않고 그대로 드러낸다

모든 값은 환경변수로 덮어쓸 수 있다 (예: LLM_TIMEOUT_WRITE=90, LLM_RETRIES=1, CIRCUIT_FAILURES=5).

사용법 — 어댑터는 "timeout을 받아 요청 1회를 보내는 함수"만 만들어 넘긴다:
    def attempt(timeout): return httpx.post(URL, json=payload, timeout=timeout).json()
    data, retries = call_sync("plan", attempt)          # 실패 시 ExternalCallError
노드에서는:
    result = await guard(deps.fast_llm.plan, query, procedure)
    if not result.ok: ... result.error["kind"] ...      # 폴백

한계(실측): httpx의 timeout은 "응답 조각 사이의 대기 시간" 기준이라, 토큰이 조금씩 계속
흘러오는 느린 스트리밍의 총 시간은 시도당 timeout으로는 제한하지 못한다 — 스트리밍 루프가
조각마다 요청 deadline을 확인해 끊는다(ollama_llm._chat_stream).
"""
import asyncio
import inspect
import os
import random
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
from langsmith import traceable

# 단계별 기본값: (시도당 타임아웃 초, 전체 시간 예산 초)
_DEFAULTS = {
    "route":   (20.0, 30.0),
    "plan":    (30.0, 45.0),
    "analyze": (30.0, 45.0),
    "chat":    (30.0, 45.0),
    "write":   (60.0, 90.0),
    "embed":   (15.0, 25.0),   # RAG 임베딩 (rag.py)
    "mcp":     (10.0, 20.0),   # MCP Tool·Resource·Prompt 호출 (graph.py)
}


class PermanentError(Exception):
    """재시도하면 안 되는 실패 — 예: 스트리밍 도중 끊겨 이미 사용자에게 토큰이 전송된 경우."""


class ExternalCallError(Exception):
    """외부 호출(LLM·MCP·임베딩)이 재시도·예산을 다 쓰고도 실패했다 — error에 구조화된 원인."""

    def __init__(self, error: dict):
        super().__init__(f"{error['stage']} {error['kind']}: {error['message']}")
        self.error = error


@dataclass
class CallResult:
    """노드가 받는 호출 결과 — ok=True면 value, ok=False면 error(dict)를 본다."""
    ok: bool
    value: Any = None
    error: dict | None = None


@dataclass(frozen=True)
class CallPolicy:
    stage: str
    timeout: float      # 시도 1회의 최대 대기 시간
    budget: float       # 재시도를 포함한 전체 최대 시간
    retries: int        # 첫 시도 이후 추가로 시도할 횟수
    base_delay: float   # 백오프 시작 간격 (시도마다 2배)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def policy_for(stage: str) -> CallPolicy:
    timeout, budget = _DEFAULTS.get(stage, (30.0, 45.0))
    key = stage.upper()
    return CallPolicy(
        stage=stage,
        timeout=_env_float(f"LLM_TIMEOUT_{key}", timeout),
        budget=_env_float(f"LLM_BUDGET_{key}", budget),
        retries=int(_env_float("LLM_RETRIES", 2)),
        base_delay=_env_float("LLM_RETRY_BASE_DELAY", 0.5),
    )


def max_tokens(json_output: bool) -> int:
    """출력 토큰 상한 — 상한이 없으면 소형 모델이 끝없이 생성(thinking 루프)할 수 있다."""
    if json_output:
        return int(_env_float("LLM_MAX_TOKENS_JSON", 512))
    return int(_env_float("LLM_MAX_TOKENS_TEXT", 1024))


def error_kind(exc: BaseException) -> str:
    """실패 종류 — 로그·LangSmith·응답의 error.kind로 쓴다."""
    if isinstance(exc, PermanentError):
        return "partial_stream"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return "rate_limited" if code == 429 else ("http_5xx" if code >= 500 else "http_4xx")
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    if isinstance(exc, (httpx.TransportError, ConnectionError, anyio.ClosedResourceError,
                        anyio.BrokenResourceError, anyio.EndOfStream)):
        return "connection"   # anyio 계열: MCP stdio 세션이 끊긴 경우
    return "error"


def is_transient(exc: BaseException) -> bool:
    """다시 시도하면 성공할 수 있는 실패인가 (타임아웃·연결 실패·5xx·429)."""
    return error_kind(exc) in ("timeout", "connection", "http_5xx", "rate_limited")


def _retry_after(exc: BaseException) -> float | None:
    """429/503 응답의 Retry-After(초) — 서버가 기다리라고 알려준 시간."""
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            return float(exc.response.headers.get("retry-after", ""))
        except ValueError:
            return None
    return None


# 요청 하나의 절대 마감 시각(time.monotonic 기준). contextvar라서 요청마다 따로 잡히고,
# 그래프 노드 task·asyncio.to_thread 스레드로도 그대로 전달된다.
_REQUEST_DEADLINE: ContextVar[float | None] = ContextVar("request_deadline", default=None)


def request_deadline_seconds() -> float:
    """요청 하나가 쓸 수 있는 총시간(초). 0이면 deadline 없음."""
    return _env_float("REQUEST_DEADLINE", 60.0)


@contextmanager
def request_deadline(seconds: float | None = None):
    """with request_deadline(): 블록 안의 모든 외부 호출이 같은 요청 deadline을 공유한다."""
    seconds = request_deadline_seconds() if seconds is None else seconds
    token = _REQUEST_DEADLINE.set(time.monotonic() + seconds if seconds > 0 else None)
    try:
        yield
    finally:
        try:
            _REQUEST_DEADLINE.reset(token)
        except ValueError:   # 스트리밍 응답처럼 다른 컨텍스트에서 끝나는 경우 — 그 컨텍스트와 함께 사라진다
            pass


def request_time_left() -> float | None:
    """요청 deadline까지 남은 시간(초). deadline이 없으면 None."""
    deadline = _REQUEST_DEADLINE.get()
    return None if deadline is None else deadline - time.monotonic()


def _service_of(stage: str) -> str:
    """서킷 브레이커를 공유하는 단위 — LLM 단계(route·plan·…)는 같은 서비스로 본다."""
    return stage if stage in ("mcp", "embed") else "llm"


class CircuitBreaker:
    """연속 실패가 threshold번 쌓이면 cooldown초 동안 열린다(호출 없이 즉시 실패).
    cooldown이 지나면 한 번 시도해 보고(half-open), 성공하면 닫힌다.
    재시도해도 소용없는 실패(4xx 등 우리 쪽 문제)는 서비스 장애가 아니므로 세지 않는다."""

    def __init__(self, name: str):
        self.name = name
        self.failures = 0
        self.opened_at: float | None = None
        self._lock = threading.Lock()   # 동기 LLM 호출은 스레드에서 돌기 때문에

    def _limits(self) -> tuple[int, float]:
        return int(_env_float("CIRCUIT_FAILURES", 3)), _env_float("CIRCUIT_COOLDOWN", 30.0)

    def check(self, stage: str) -> None:
        threshold, cooldown = self._limits()
        with self._lock:
            if self.opened_at is not None and time.monotonic() - self.opened_at < cooldown:
                left = cooldown - (time.monotonic() - self.opened_at)
                raise ExternalCallError({
                    "stage": stage, "kind": "circuit_open", "retryable": False, "attempts": 0,
                    "elapsed_s": 0.0,
                    "message": f"{self.name} 연속 {self.failures}회 실패 — {left:.0f}초 동안 호출 중단"})

    def record(self, ok: bool, counts_as_outage: bool = True) -> None:
        threshold, _ = self._limits()
        with self._lock:
            if ok:
                self.failures, self.opened_at = 0, None
            elif counts_as_outage:
                self.failures += 1
                if self.failures >= threshold:
                    self.opened_at = time.monotonic()   # 열기 (half-open 시도가 실패하면 다시 연장)


_BREAKERS = {name: CircuitBreaker(name) for name in ("llm", "mcp", "embed")}


def breaker_for(stage: str) -> CircuitBreaker:
    return _BREAKERS[_service_of(stage)]


def reset_breakers() -> None:
    """테스트·평가에서 이전 실행의 차단 상태를 지운다."""
    for b in _BREAKERS.values():
        b.failures, b.opened_at = 0, None


class _Attempts:
    """한 번의 논리적 호출에서 시도 간격과 남은 예산을 계산한다 (sync/async 공용).

    예) route: timeout 20초, budget 30초 → 1차 시도 20초 대기 후 실패 → 약 0.5초 쉬고 →
        2차 시도는 남은 약 9.5초만 기다린다 → 그래도 실패하면 ExternalCallError → graph가 폴백."""

    def __init__(self, policy: CallPolicy):
        self.policy = policy
        self.started = time.monotonic()
        # 단계 예산과 요청 deadline 중 먼저 오는 시각 — 이 시각을 넘기면 더 시도하지 않는다
        request_deadline_at = _REQUEST_DEADLINE.get()
        self.deadline = self.started + policy.budget
        if request_deadline_at is not None:
            self.deadline = min(self.deadline, request_deadline_at)
        self.attempt = 0

    def check_deadline(self) -> None:
        """시도하기 전에 확인 — 시간이 남지 않았으면 호출하지 않고 즉시 실패한다."""
        if self.deadline - time.monotonic() <= 0.05:
            raise ExternalCallError({
                "stage": self.policy.stage, "kind": "deadline", "retryable": False,
                "attempts": self.attempt, "elapsed_s": round(time.monotonic() - self.started, 2),
                "message": "요청 deadline 초과 — 호출하지 않고 폴백"})

    def next_timeout(self) -> float:
        # 시도당 타임아웃과 남은 예산 중 작은 값 (0 이하로 내려가 httpx가 오동작하지 않게 최소 0.1초)
        return max(0.1, min(self.policy.timeout, self.deadline - time.monotonic()))

    def _give_up(self, exc: BaseException) -> ExternalCallError:
        return ExternalCallError({
            "stage": self.policy.stage, "kind": error_kind(exc), "retryable": is_transient(exc),
            "attempts": self.attempt, "elapsed_s": round(time.monotonic() - self.started, 2),
            "message": f"{type(exc).__name__}: {str(exc)[:200]}"})

    def backoff_or_raise(self, exc: BaseException) -> float:
        """재시도할 수 있으면 기다릴 시간을 돌려주고, 아니면 ExternalCallError를 던진다."""
        delay = self.policy.base_delay * (2 ** (self.attempt - 1))   # 0.5 → 1.0 → 2.0초…
        delay *= random.uniform(0.8, 1.2)        # 지터: 여러 요청이 같은 순간에 몰려 재시도하지 않게
        server_hint = _retry_after(exc)
        if server_hint is not None:              # 서버가 알려준 대기 시간이 있으면 그걸 따른다
            delay = server_hint
        remaining = self.deadline - time.monotonic()
        # 포기하는 세 경우: ① 재시도해도 소용없는 실패(4xx 등) ② 재시도 횟수 소진
        # ③ 쉬고 나면 예산이 남지 않음
        if (not is_transient(exc) or self.attempt > self.policy.retries
                or remaining <= delay + 0.1):
            raise self._give_up(exc) from exc
        return delay


def _finish(stage: str, exc: ExternalCallError | None) -> None:
    """논리적 호출 1번의 성공/실패를 서킷 브레이커에 반영한다."""
    breaker_for(stage).record(exc is None, counts_as_outage=exc is None or exc.error["retryable"])


@traceable(name="resilience.call_sync")
def call_sync(stage: str, fn):
    """fn(timeout) -> result 를 정책대로 호출한다. (결과, 재시도 횟수)를 돌려준다.
    재시도를 다 쓰면 ExternalCallError — 원래 예외는 __cause__로 남는다."""
    breaker_for(stage).check(stage)
    tracker = _Attempts(policy_for(stage))
    while True:
        tracker.check_deadline()
        tracker.attempt += 1
        try:
            result = fn(tracker.next_timeout())
        except Exception as exc:
            try:
                delay = tracker.backoff_or_raise(exc)
            except ExternalCallError as final:
                _finish(stage, final)
                raise
            # 동기 sleep — graph의 guard가 동기 호출을 asyncio.to_thread로 돌리므로
            # 이 대기는 별도 스레드에서 일어나 이벤트 루프(다른 요청)를 막지 않는다
            time.sleep(delay)
            continue
        _finish(stage, None)
        return result, tracker.attempt - 1


@traceable(name="resilience.call_async")
async def call_async(stage: str, fn):
    """await fn(timeout) -> result 를 정책대로 호출한다. (결과, 재시도 횟수)를 돌려준다."""
    breaker_for(stage).check(stage)
    tracker = _Attempts(policy_for(stage))
    while True:
        tracker.check_deadline()
        tracker.attempt += 1
        try:
            result = await fn(tracker.next_timeout())
        except Exception as exc:
            try:
                delay = tracker.backoff_or_raise(exc)
            except ExternalCallError as final:
                _finish(stage, final)
                raise
            await asyncio.sleep(delay)
            continue
        _finish(stage, None)
        return result, tracker.attempt - 1


async def guard(fn, *args, **kwargs) -> CallResult:
    """노드용 경계 — 외부 호출 실패만 CallResult(ok=False, error=...)로 바꾼다.

    - 동기 함수(route·plan·analyze·rag.classify)는 asyncio.to_thread로 돌려 이벤트 루프를 막지 않는다
      (contextvars가 복사되므로 LangSmith 부모 run도 그대로 이어진다)
    - ExternalCallError 외의 예외는 잡지 않는다 — 우리 코드의 버그가 "LLM 장애"로 둔갑해
      폴백 뒤에 숨는 것을 막기 위해서다 (baseline·이전 버전의 except Exception 문제)
    """
    try:
        if inspect.iscoroutinefunction(fn):
            value = await fn(*args, **kwargs)
        else:
            value = await asyncio.to_thread(fn, *args, **kwargs)
        return CallResult(ok=True, value=value)
    except ExternalCallError as exc:
        return CallResult(ok=False, error=exc.error)
