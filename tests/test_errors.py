"""agent/errors.py — 일시 오류만 재시도하고, 그 밖의 실패는 바로 올린다."""
import asyncio

import httpx
import pytest

from agent.errors import RETRIES, is_transient, retry_async, retry_sync

REQUEST = httpx.Request("POST", "http://llm")


def _status(code: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError("status", request=REQUEST, response=httpx.Response(code, request=REQUEST))


@pytest.mark.parametrize("exc, expected", [
    (httpx.ReadTimeout("t", request=REQUEST), True),
    (httpx.ConnectError("c", request=REQUEST), True),
    (asyncio.TimeoutError(), True),
    (ConnectionError(), True),
    (_status(503), True),
    (_status(429), True),
    (_status(400), False),
    (KeyError("bug"), False),
])
def test_is_transient(exc, expected):
    assert is_transient(exc) is expected


def test_retry_recovers_from_a_transient_failure():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("down", request=REQUEST)
        return "ok"

    assert retry_sync(flaky) == ("ok", 1)


def test_retry_gives_up_after_the_limit():
    calls = []

    def dead():
        calls.append(1)
        raise httpx.ReadTimeout("no response", request=REQUEST)

    with pytest.raises(httpx.ReadTimeout):
        retry_sync(dead)
    assert len(calls) == RETRIES + 1


def test_client_errors_are_not_retried():
    calls = []

    async def bad_request():
        calls.append(1)
        raise _status(400)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(retry_async(bad_request))
    assert len(calls) == 1
