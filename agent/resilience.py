"""LLM 호출 방어선 — 단계별 타임아웃 · 일시 오류 재시도 · 전체 시간 예산 · 출력 토큰 상한.

baseline은 LLM 호출 하나에 timeout 300초(Ollama)/120초(OpenAI)만 걸려 있고 재시도가 없어,
모델이 응답하지 않으면 그 시간을 통째로 기다린 뒤 예외가 그래프 밖으로 터졌다(실측: 302초 후
HTTP 500). 여기서는 호출 단계(stage)마다 정책을 따로 두고 어댑터(openai_llm/ollama_llm)의
저수준 호출을 감싼다.

- 시도당 타임아웃: route 같은 짧은 분류와 write 같은 긴 생성의 정상 소요 시간이 다르므로 단계별로 둔다
- 재시도: 일시 오류(타임아웃·연결 실패·5xx·429)만 지수 백오프로 재시도, 그 외 4xx 등은 즉시 전파
  (retry.py의 Wave 9 원칙을 LLM 호출로 확장)
- 전체 시간 예산: 재시도까지 합친 상한 — 남은 예산이 시도당 타임아웃보다 작으면 남은 만큼만 기다린다
- 출력 토큰 상한: JSON 출력(route/plan)과 텍스트 출력(chat/write/analyze)을 나눠 둔다

모든 값은 환경변수로 덮어쓸 수 있다 (예: LLM_TIMEOUT_WRITE=90, LLM_RETRIES=1).
"""
import asyncio
import os
import time
from dataclasses import dataclass

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
}


class PermanentError(Exception):
    """재시도하면 안 되는 실패 — 예: 스트리밍 도중 끊겨 이미 사용자에게 토큰이 전송된 경우."""


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


def is_transient(exc: BaseException) -> bool:
    """다시 시도하면 성공할 수 있는 실패인가."""
    if isinstance(exc, PermanentError):
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code == 429
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


class _Attempts:
    """한 번의 논리적 호출에서 시도 간격과 남은 예산을 계산한다 (sync/async 공용)."""

    def __init__(self, policy: CallPolicy):
        self.policy = policy
        self.deadline = time.monotonic() + policy.budget
        self.attempt = 0

    def next_timeout(self) -> float:
        return max(0.1, min(self.policy.timeout, self.deadline - time.monotonic()))

    def backoff_or_raise(self, exc: BaseException) -> float:
        """재시도할 수 있으면 기다릴 시간을 돌려주고, 아니면 예외를 그대로 다시 던진다."""
        delay = self.policy.base_delay * (2 ** (self.attempt - 1))
        remaining = self.deadline - time.monotonic()
        if (not is_transient(exc) or self.attempt > self.policy.retries
                or remaining <= delay + 0.1):
            raise exc
        return delay


@traceable(name="resilience.call_sync")
def call_sync(stage: str, fn):
    """fn(timeout) -> result 를 정책대로 호출한다. (결과, 재시도 횟수)를 돌려준다."""
    tracker = _Attempts(policy_for(stage))
    while True:
        tracker.attempt += 1
        try:
            return fn(tracker.next_timeout()), tracker.attempt - 1
        except Exception as exc:
            time.sleep(tracker.backoff_or_raise(exc))


@traceable(name="resilience.call_async")
async def call_async(stage: str, fn):
    """await fn(timeout) -> result 를 정책대로 호출한다. (결과, 재시도 횟수)를 돌려준다."""
    tracker = _Attempts(policy_for(stage))
    while True:
        tracker.attempt += 1
        try:
            return await fn(tracker.next_timeout()), tracker.attempt - 1
        except Exception as exc:
            await asyncio.sleep(tracker.backoff_or_raise(exc))
