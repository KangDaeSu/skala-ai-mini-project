"""장애 주입기 — httpx 전송 계층을 monkeypatch해 LLM API 호출에 일부러 장애를 낸다.

agent/ 코드는 전혀 바꾸지 않는다. openai_llm.py·ollama_llm.py가 쓰는 httpx의 전송 계층
(HTTPTransport / AsyncHTTPTransport)만 가로채므로, Before/After 어느 코드에도 같은
조건이 걸린다. 장애 여부는 (seed, 쿼리 id, 반복 회차, 그 쿼리 안에서 몇 번째 호출인지)의
해시로 정하므로 같은 seed면 Before와 After가 같은 위치에서 같은 장애를 맞는다.

시나리오
- hang    : 요청에 설정된 read timeout만큼 실제로 기다린 뒤 httpx.ReadTimeout (응답 없음)
- error   : 503 Service Unavailable
- badjson : JSON 출력을 강제한 요청(route/plan)에 잘린 JSON을 돌려준다
            (JSON 모드가 아닌 요청에는 적용하지 않고 정상 통과)
"""
import asyncio
import hashlib
import json
import time

import httpx

_orig_sync = httpx.HTTPTransport.handle_request
_orig_async = httpx.AsyncHTTPTransport.handle_async_request


class _State:
    installed = False
    enabled = False
    hosts: set[str] = set()
    rates: list[tuple[str, float]] = []
    seed = 42
    qid = ""
    rep = 0
    call_idx = 0
    injected: list[dict] = []


S = _State()


def parse_rates(text: str) -> list[tuple[str, float]]:
    """"hang=0.15,error=0.10,badjson=0.10" → [("hang", 0.15), ...]"""
    pairs = []
    for part in text.split(","):
        name, value = part.split("=")
        if name.strip() not in ("hang", "error", "badjson"):
            raise ValueError(f"알 수 없는 장애 유형: {name}")
        pairs.append((name.strip(), float(value)))
    return pairs


def _is_json_mode(request: httpx.Request) -> bool:
    try:
        body = json.loads(request.content or b"{}")
    except (json.JSONDecodeError, httpx.RequestNotRead):
        return False
    return "response_format" in body or "format" in body   # OpenAI JSON 모드 / Ollama 스키마


def _decide(request: httpx.Request) -> str | None:
    if not S.enabled or request.url.host not in S.hosts:
        return None
    k = S.call_idx
    S.call_idx += 1
    digest = hashlib.sha256(f"{S.seed}|{S.qid}|{S.rep}|{k}".encode()).digest()
    u = int.from_bytes(digest[:8], "big") / 2 ** 64
    cum = 0.0
    for name, rate in S.rates:
        cum += rate
        if u < cum:
            if name == "badjson" and not _is_json_mode(request):
                return None
            S.injected.append({"call": k, "fault": name, "url": str(request.url)})
            return name
    return None


def _timeout_of(request: httpx.Request) -> float:
    return (request.extensions.get("timeout") or {}).get("read") or 30.0


def _response(request: httpx.Request, fault: str) -> httpx.Response:
    if fault == "error":
        return httpx.Response(503, json={"error": {"message": "chaos: service unavailable"}},
                              request=request)
    truncated = '{"route": "inci'   # 잘린 JSON
    if request.url.host == "api.openai.com":
        body = {"choices": [{"message": {"role": "assistant", "content": truncated}}],
                "usage": {"total_tokens": 0}}
    else:   # Ollama /api/chat
        body = {"message": {"role": "assistant", "content": truncated},
                "prompt_eval_count": 0, "eval_count": 0, "done": True}
    return httpx.Response(200, json=body, request=request)


def _patched_sync(self, request):
    fault = _decide(request)
    if fault == "hang":
        time.sleep(_timeout_of(request))
        raise httpx.ReadTimeout("chaos: simulated hang", request=request)
    if fault:
        return _response(request, fault)
    return _orig_sync(self, request)


async def _patched_async(self, request):
    fault = _decide(request)
    if fault == "hang":
        await asyncio.sleep(_timeout_of(request))
        raise httpx.ReadTimeout("chaos: simulated hang", request=request)
    if fault:
        return _response(request, fault)
    return await _orig_async(self, request)


def install(hosts: set[str], rates: list[tuple[str, float]], seed: int) -> None:
    S.hosts, S.rates, S.seed = hosts, rates, seed
    if not S.installed:
        httpx.HTTPTransport.handle_request = _patched_sync
        httpx.AsyncHTTPTransport.handle_async_request = _patched_async
        S.installed = True


def begin(qid: str, rep: int) -> None:
    """측정할 쿼리 1건 시작 — 호출 순번을 0으로 되돌리고 장애 주입을 켠다."""
    S.qid, S.rep, S.call_idx, S.injected = qid, rep, 0, []
    S.enabled = True


def end() -> list[dict]:
    """장애 주입을 끄고, 이번 쿼리에 실제로 주입된 장애 목록을 돌려준다."""
    S.enabled = False
    return list(S.injected)
