"""all_total 통합 실습 — FastAPI 백엔드 (Wave 1·3·12·14 축 + 전체 조립).

- Wave 1  : lifespan에서 Agent 번들(MCP 연결·LLM·그래프)을 프로세스당 정확히 1회 생성,
            app.state로 모든 요청이 공유 (creation_count/instance_id로 증명)
- Wave 2  : mcp_server.py를 subprocess(stdio)로 기동해 연결 유지
- Wave 3  : GET /chat/stream — 그래프 실행 과정을 SSE 이벤트로 스트리밍
- Wave 12 : 대화 이력을 SQLite(session.db)에 저장 — 재시작해도 유지
- Wave 14 : SUPERVISOR_VERSION(v1/v2) 환경변수로 legacy/신형 파이프라인 즉시 전환
- LangSmith: 요청당 chat_request 루트 run 아래로 노드·LLM·MCP 호출이 계층 기록됨
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()   # LANGCHAIN_TRACING_V2 / API_KEY / PROJECT — import보다 먼저

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from pydantic import BaseModel

from agent.deps import SupervisorDeps
from agent.errors import EXTERNAL, REQUEST_TIMEOUT, error_info
from agent.fake_llm import FastLLM, QualityLLM
from agent.fallback import tag_request_run
from agent.graph import build_graph
from agent.mcp_client import MCPClient
from agent.rag import build_retriever
from agent.session_store import SqliteSessionStore
from agent.supervisor_v1 import run_v1

CREATION_COUNT = 0   # Wave 1 — 프로세스 내 Agent 번들 생성 횟수 (항상 1이어야 정상)


class ChatRequest(BaseModel):   # Wave 1 — Pydantic 요청 검증
    message: str
    thread_id: str = "default"


def _build_llms():
    """LLM_BACKEND=fake(기본, 결정론) | ollama(로컬 실모델) | openai(실제 OpenAI API)."""
    backend = os.environ.get("LLM_BACKEND", "fake")
    if backend == "ollama":
        from agent.ollama_llm import OllamaFastLLM, OllamaQualityLLM
        fast = OllamaFastLLM(os.environ.get("OLLAMA_FAST_MODEL", "qwen3:0.6b"),
                             usd_per_1k_tokens=0.00015)
        quality = OllamaQualityLLM(os.environ.get("OLLAMA_QUALITY_MODEL", "qwen3:8b"),
                                   usd_per_1k_tokens=0.005)
        return backend, fast, quality
    if backend == "openai":
        from agent.openai_llm import OpenAIFastLLM, OpenAIQualityLLM
        fast = OpenAIFastLLM(os.environ.get("OPENAI_FAST_MODEL", "gpt-4o-mini"),
                             usd_per_1k_tokens=0.00015)
        quality = OpenAIQualityLLM(os.environ.get("OPENAI_QUALITY_MODEL", "gpt-4o"),
                                   usd_per_1k_tokens=0.005)
        return backend, fast, quality
    fast = FastLLM("fast-model-stub", usd_per_1k_tokens=0.00015)
    quality = QualityLLM("quality-model-stub", usd_per_1k_tokens=0.005)
    return backend, fast, quality


@asynccontextmanager
async def lifespan(app: FastAPI):
    global CREATION_COUNT
    CREATION_COUNT += 1
    mcp = MCPClient()
    await mcp.start()   # Wave 2 — MCP subprocess는 서버 수명 동안 딱 1개
    backend, fast_llm, quality_llm = _build_llms()
    app.state.llm_backend = backend
    deps = SupervisorDeps(
        fast_llm=fast_llm,
        quality_llm=quality_llm,
        mcp=mcp,
        session_store=SqliteSessionStore(),
        version=os.environ.get("SUPERVISOR_VERSION", "v2"),
        retriever=build_retriever(backend),   # runbook 인덱스는 기동 시 1회만 임베딩
    )
    app.state.deps = deps
    app.state.graph = build_graph(deps) if deps.version == "v2" else None
    app.state.instance_id = id(deps)
    yield
    await mcp.stop()
    deps.session_store.close()
    try:   # 종료 전 LangSmith 배치 전송 플러시 — kill 시 run이 pending으로 남는 것 방지
        from langchain_core.tracers.langchain import wait_for_all_tracers
        wait_for_all_tracers()
    except Exception:
        pass


app = FastAPI(lifespan=lifespan)


def _error_body(error: dict) -> dict:
    """모든 실패 응답의 공통 형태 — 클라이언트는 ok만 보고 성공/실패를 가른다."""
    return {"ok": False, "reply": None, "error": error}


def _internal_error(exc: BaseException) -> dict:
    return {"stage": "server", "kind": "internal", "retryable": False,
            "message": f"{type(exc).__name__}: {str(exc)[:300]}"}


def _failure(exc: BaseException) -> tuple[int, dict]:
    """외부 호출 실패·요청 시간 초과는 503(잠시 후 재시도 가능), 그 밖의 예외(버그)는 500."""
    if isinstance(exc, EXTERNAL):
        return 503, {"stage": "server", **error_info(exc)}
    return 500, _internal_error(exc)


def _session_warning(action: str, exc: Exception) -> dict:
    """세션 저장소(SQLite) 실패 — 대화 이력은 부가 기능이라 답변을 막지 않고 Degraded로만 남긴다."""
    reason = ("대화 이력 조회 실패 → 이력 없이 진행" if action == "load"
              else "대화 이력 저장 실패 → 답변은 그대로 반환")
    return {"type": "Degraded", "stage": "session", "reason": reason,
            "error": {"stage": "session", "kind": "storage", "retryable": False,
                      "message": f"{type(exc).__name__}: {str(exc)[:200]}"}}


def _load_history(deps, thread_id: str) -> tuple[list[dict], dict | None]:
    try:
        return deps.session_store.load(thread_id), None
    except Exception as exc:   # baseline: 이력 조회 실패가 요청 전체를 500으로 만들었다
        return [], _session_warning("load", exc)


def _save_turn(deps, thread_id: str, message: str, reply: str) -> dict | None:
    try:
        deps.session_store.append(thread_id, "user", message)
        deps.session_store.append(thread_id, "assistant", reply)
        return None
    except Exception as exc:
        return _session_warning("save", exc)


@app.exception_handler(Exception)
async def _unexpected_failure(request: Request, exc: Exception):
    """그래프가 폴백하지 못한 실패도 구조 없는 'Internal Server Error' 대신 같은 형태로 내려준다."""
    status, error = _failure(exc)
    return JSONResponse(status_code=status, content=_error_body(error))


@app.get("/health")
async def health():
    return {"status": "ok", "instance_id": app.state.instance_id,
            "creation_count": CREATION_COUNT,
            "supervisor_version": app.state.deps.version,
            "llm_backend": app.state.llm_backend,
            "fast_llm": app.state.deps.fast_llm.name,
            "quality_llm": app.state.deps.quality_llm.name,
            "runbook_classifier": (f"rag({app.state.deps.retriever.embedder.name})"
                                   if app.state.deps.retriever else "keyword")}


@app.get("/version")
async def version():
    return {"supervisor_version": app.state.deps.version}


def _metadata(result: dict, run_id: str | None) -> dict:
    return {
        "route": result.get("route"),
        "task_count": len(result.get("tasks", [])),
        "gate_removed": result.get("gate_removed", 0),
        "replan_rounds": result.get("replan_rounds", 0),
        "retry_count": result.get("retry_count", 0),
        "parallel_elapsed": result.get("parallel_elapsed"),
        "validation_attempts": result.get("validation_attempts", 0),
        "cost_usd": result.get("cost_usd", 0.0),
        "degraded_count": len(result.get("degraded", [])),   # 외부 호출·이력 실패로 폴백한 단계 수
        "request_timeout_s": REQUEST_TIMEOUT,                 # 요청 하나가 쓸 수 있는 총시간
        "llm_backend": app.state.llm_backend,
        "supervisor_version": app.state.deps.version,
        "instance_id": app.state.instance_id,
        "langsmith_run_id": run_id,
    }


@traceable(name="chat_request")
async def _handle_chat(message: str, thread_id: str) -> tuple[dict, str | None]:
    """/chat 처리 — 이력 로드 → 그래프 실행(요청 상한 안에서) → 이력 저장."""
    deps = app.state.deps
    history, load_warning = _load_history(deps, thread_id)   # Wave 12 — 실패해도 이력 없이 진행
    async with asyncio.timeout(REQUEST_TIMEOUT):   # 요청 전체 시간 상한 — 넘으면 TimeoutError → 503
        if deps.version == "v2":
            result = await app.state.graph.ainvoke(
                {"query": message, "thread_id": thread_id, "history": history,
                 "events": [], "cost_usd": 0.0})
        else:
            result = await run_v1(deps, message, thread_id, history)   # Wave 14
    save_warning = _save_turn(deps, thread_id, message, result["final"])
    warnings = [w for w in (load_warning, save_warning) if w]
    if warnings:
        result["degraded"] = result.get("degraded", []) + warnings
        result["events"] = result.get("events", []) + warnings
    tag_request_run(result)   # 폴백이 있었으면 루트 run에 degraded 태그
    rt = get_current_run_tree()
    return result, (str(rt.id) if rt else None)


@app.post("/chat")
async def chat(req: ChatRequest):
    result, run_id = await _handle_chat(req.message, req.thread_id)
    degraded = result.get("degraded", [])
    # ok=True: 답변이 나왔다. 일부 단계가 폴백했으면 degraded에 단계별 구조화된 원인이 담긴다
    return {"ok": True, "reply": result["final"], "error": None,
            "degraded": [{"stage": d["stage"], "reason": d["reason"], "error": d.get("error")}
                         for d in degraded],
            "events": result.get("events", []), "metadata": _metadata(result, run_id)}


async def _stream_graph(inputs: dict):
    """그래프 스트림을 요청 전체 시간 상한(REQUEST_TIMEOUT) 안에서 흘려보낸다.

    그래프는 별도 task에서 돌며 이벤트를 큐에 넣고, 여기서는 큐에서 꺼내 보낸다. 상한을
    넘기면 task가 TimeoutError로 끝나고, 그 예외가 아래 raise로 올라가 Error 이벤트가 된다."""
    queue: asyncio.Queue = asyncio.Queue()
    done = object()

    async def produce():
        try:
            async for item in app.state.graph.astream(inputs, stream_mode=["updates", "custom"]):
                await queue.put(item)
        finally:
            await queue.put(done)

    task = asyncio.create_task(asyncio.wait_for(produce(), REQUEST_TIMEOUT))
    while (item := await queue.get()) is not done:
        yield item
    await task   # 그래프가 실패·시간 초과로 끝났으면 여기서 예외가 올라온다


@app.get("/chat/stream")
async def chat_stream(message: str, thread_id: str = "default"):
    """Wave 3 — 그래프의 노드별 진행 상황을 SSE로 스트리밍.

    이벤트마다 'data: {json}\\n\\n' 형태로 내려보내고 마지막에 data: [DONE] 센티널을
    보낸다 — 프론트엔드는 \\n\\n 경계로 이벤트를 분리해 파싱해야 한다(Wave 3b).
    """
    deps = app.state.deps

    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def gen():
        # 스트리밍 도중의 예외는 HTTP 상태로 알릴 수 없다(헤더가 이미 나감) — baseline은 연결이
        # 조용히 끊겼다. Error 이벤트로 구조화해 보내고 [DONE]으로 정상 종료한다.
        try:
            async for chunk in run():
                yield chunk
        except Exception as exc:
            yield sse({"type": "Error", "ok": False, "error": _failure(exc)[1]})
        yield "data: [DONE]\n\n"

    async def run():
        history, load_warning = _load_history(deps, thread_id)
        if load_warning:
            yield sse({**load_warning, "node": "session"})
        if deps.version != "v2":
            async with asyncio.timeout(REQUEST_TIMEOUT):
                result = await run_v1(deps, message, thread_id, history)
            for ev in result["events"]:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'FinalAnswer', 'reply': result['final']}, ensure_ascii=False)}\n\n"
        else:
            seen = 0
            final = ""
            last_prompt = None   # finalize까지 살아남은 최종 write/chat 호출의 실제 프롬프트
            # stream_mode를 리스트로 주면 (mode, payload) 튜플이 나온다 — "updates"는
            # 노드가 끝날 때마다의 상태 델타, "custom"은 write_node/chat_answer_node가
            # get_stream_writer()로 실행 중에 즉시 흘려보내는 토큰(AnswerToken) 이벤트다.
            async for mode, payload in _stream_graph(
                    {"query": message, "thread_id": thread_id, "history": history,
                     "events": [], "cost_usd": 0.0}):
                if mode == "custom":
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    continue
                for node_name, delta in payload.items():
                    for ev in (delta.get("events") or [])[seen:]:
                        ev = {**ev, "node": node_name}
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    if delta.get("events"):
                        seen = len(delta["events"])
                    if delta.get("final"):
                        final = delta["final"]
                    if delta.get("last_prompt"):
                        last_prompt = delta["last_prompt"]
            save_warning = _save_turn(deps, thread_id, message, final)
            if save_warning:
                yield sse({**save_warning, "node": "session"})
            yield sse({"type": "FinalAnswer", "ok": True, "reply": final, "prompt": last_prompt})

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="warning")
