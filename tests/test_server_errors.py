"""server.py — 실패 응답의 형태와 세션 저장소 실패 시의 동작."""
from fastapi.testclient import TestClient

import server
from agent.deps import SupervisorDeps
from agent.fake_llm import FastLLM, QualityLLM
from agent.graph import build_graph
from tests.test_graph_fallback import FakeMCP


class _BrokenSessionStore:
    """SQLite가 잠기거나 디스크가 꽉 찬 상황 — 조회·저장 모두 실패."""

    def load(self, thread_id):
        raise RuntimeError("database is locked")

    def append(self, thread_id, role, content):
        raise RuntimeError("disk I/O error")


def _client() -> TestClient:
    # lifespan을 돌리지 않는다 — MCP·LLM 없이 필요한 상태만 직접 넣는다
    return TestClient(server.app, raise_server_exceptions=False)


def _install_fake_app(session_store) -> None:
    deps = SupervisorDeps(fast_llm=FastLLM("fake", 0.0), quality_llm=QualityLLM("fake", 0.0),
                          mcp=FakeMCP(), session_store=session_store, version="v2")
    server.app.state.deps, server.app.state.graph = deps, build_graph(deps)
    server.app.state.llm_backend, server.app.state.instance_id = "fake", 0


def _clear_app_state() -> None:
    for name in ("deps", "graph", "llm_backend", "instance_id"):
        if hasattr(server.app.state, name):
            delattr(server.app.state, name)


def test_unexpected_exception_returns_structured_json():
    _clear_app_state()
    response = _client().get("/health")   # app.state가 비어 있어 AttributeError가 난다
    body = response.json()
    assert response.status_code == 500
    assert body["ok"] is False and body["reply"] is None
    assert body["error"]["kind"] == "internal" and "AttributeError" in body["error"]["message"]


def test_session_store_failure_does_not_block_the_answer():
    """이력 조회·저장이 실패해도 답변은 나온다 — 실패는 degraded에 구조화돼 남는다."""
    _install_fake_app(_BrokenSessionStore())
    try:
        body = _client().post("/chat", json={"message": "payments-service 진단해줘"}).json()
    finally:
        _clear_app_state()
    assert body["ok"] is True and body["reply"]
    session = [d for d in body["degraded"] if d["stage"] == "session"]
    assert [d["error"]["kind"] for d in session] == ["storage", "storage"]   # 조회 + 저장
    assert "database is locked" in session[0]["error"]["message"]
    assert body["metadata"]["degraded_count"] >= 2


def test_stream_reports_session_failure_and_still_answers():
    _install_fake_app(_BrokenSessionStore())
    try:
        text = _client().get("/chat/stream", params={"message": "payments-service 진단해줘"}).text
    finally:
        _clear_app_state()
    assert '"stage": "session"' in text
    assert '"type": "FinalAnswer", "ok": true' in text
    assert text.rstrip().endswith("data: [DONE]")


def test_stream_failure_is_sent_as_error_event():
    """그래프 밖에서 터진 예외는 HTTP 상태로 알릴 수 없다 — Error 이벤트 후 [DONE]."""
    _install_fake_app(_BrokenSessionStore())
    del server.app.state.graph   # 그래프가 없는 잘못된 상태
    try:
        text = _client().get("/chat/stream", params={"message": "안녕"}).text
    finally:
        _clear_app_state()
    assert '"type": "Error"' in text and '"ok": false' in text
    assert text.rstrip().endswith("data: [DONE]")
