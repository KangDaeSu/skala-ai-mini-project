"""외부 호출(LLM·MCP·임베딩) 실패 처리 — timeout, 일시 오류 재시도, 노드가 잡을 예외 목록.

강의 10장 Error Handling(Transient Error → with_retry → Exponential Backoff)을 LLM·MCP·임베딩
호출 전체로 넓힌 것이다. baseline은 MCP 모니터링 조회 한 곳에서 asyncio.TimeoutError만
재시도했고, LLM은 timeout 300초(Ollama)/120초(OpenAI) 1회에 예외 처리가 없었다.

- 응답이 없으면 예외 자체가 나지 않으므로, 먼저 timeout으로 "응답 없음"을 예외로 바꾼다
- 다시 시도하면 될 실패(TRANSIENT, 5xx·429)만 재시도하고, 그 외(4xx)는 바로 포기한다
- 노드는 EXTERNAL만 잡아 폴백한다. 그 밖의 예외는 우리 코드의 버그라 잡지 않는다
"""
import asyncio
import os
import time

import anyio
import httpx

# 단계별 시도 1회의 timeout(초) — 짧은 분류(route)와 긴 생성(write)의 정상 소요 시간이 다르다.
# 실측 최대(OpenAI / Ollama): fast 모델 2.1 / 1.3초, write 5.1 / 13.5초. 요청 상한(60초) 안에
# 응답 없음 1회 + 재시도가 들어가도록 잡았다 (write 60초였을 때는 응답 없음 1번에 요청 전체가 끝났다)
TIMEOUTS = {"route": 10, "plan": 15, "analyze": 15, "chat": 15, "write": 30, "embed": 10, "mcp": 5}
RETRIES = 2                                                      # 첫 시도 이후 추가 시도 횟수
BASE_DELAY = float(os.environ.get("LLM_RETRY_BASE_DELAY", 0.5))  # 0.5초 → 1초 (지수 백오프)
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", 60))   # 요청 하나의 전체 상한 (server.py)
MAX_TOKENS = {"json": 512, "text": 1024}   # 출력 토큰 상한 — 소형 모델이 끝없이 생성하는 것을 막는다

# 다시 시도하면 성공할 수 있는 실패: 응답 없음·연결 실패·MCP stdio 세션 끊김
TRANSIENT = (httpx.TransportError, TimeoutError, ConnectionError,
             anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream)
# 노드가 잡아서 폴백하는 외부 호출 실패 (HTTP 4xx·5xx 응답 포함)
EXTERNAL = TRANSIENT + (httpx.HTTPStatusError,)


def is_transient(exc: BaseException) -> bool:
    """다시 시도하면 성공할 수 있는 실패인가 — 재시도 여부와 error.retryable의 기준."""
    if isinstance(exc, httpx.HTTPStatusError):   # 5xx·429는 서버 쪽 일시 문제, 4xx는 요청 자체의 문제
        code = exc.response.status_code
        return code >= 500 or code == 429
    return isinstance(exc, TRANSIENT)


def _delay(attempt: int) -> float:
    return BASE_DELAY * (2 ** attempt)


def retry_sync(fn):
    """fn()을 일시 오류일 때만 최대 RETRIES번 다시 호출한다. (결과, 재시도 횟수)를 돌려준다."""
    for attempt in range(RETRIES + 1):
        try:
            return fn(), attempt
        except Exception as exc:
            if not is_transient(exc) or attempt == RETRIES:
                raise
            time.sleep(_delay(attempt))


async def retry_async(fn):
    """await fn()을 일시 오류일 때만 최대 RETRIES번 다시 호출한다. (결과, 재시도 횟수)를 돌려준다."""
    for attempt in range(RETRIES + 1):
        try:
            return await fn(), attempt
        except Exception as exc:
            if not is_transient(exc) or attempt == RETRIES:
                raise
            await asyncio.sleep(_delay(attempt))


async def call_mcp(fn, *args, **kwargs):
    """MCP 호출 — 시도마다 10초 timeout(baseline: timeout 없음), 일시 오류는 재시도.
    (결과, 재시도 횟수)를 돌려주고, 끝내 실패하면 예외를 그대로 올린다."""
    return await retry_async(lambda: asyncio.wait_for(fn(*args, **kwargs), TIMEOUTS["mcp"]))


def error_info(exc: BaseException) -> dict:
    """폴백 기록·응답에 남길 실패 정보."""
    return {"kind": type(exc).__name__, "retryable": is_transient(exc),
            "message": str(exc)[:200] or type(exc).__name__}


def describe(exc: BaseException) -> str:
    """사람이 읽는 한 줄 — 예: "ReadTimeout: timed out"."""
    message = str(exc)[:80]
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
