"""server.py — 처리하지 못한 예외도 구조 없는 500 대신 {ok: false, error: {...}}로 내려가는지."""
from fastapi.testclient import TestClient

import server


class _BrokenSessionStore:
    def load(self, thread_id):
        raise RuntimeError("session db unavailable")


class _BrokenDeps:
    version = "v2"
    session_store = _BrokenSessionStore()


def _client() -> TestClient:
    # lifespan을 돌리지 않는다 — MCP·LLM 없이 실패 경로만 본다
    return TestClient(server.app, raise_server_exceptions=False)


def test_unexpected_exception_returns_structured_json():
    if hasattr(server.app.state, "deps"):
        del server.app.state.deps
    response = _client().get("/health")   # app.state가 비어 있어 AttributeError가 난다
    body = response.json()
    assert response.status_code == 500
    assert body["ok"] is False and body["reply"] is None
    assert body["error"]["kind"] == "internal" and "AttributeError" in body["error"]["message"]


def test_stream_failure_is_sent_as_error_event():
    """스트리밍 도중 예외는 HTTP 상태로 알릴 수 없다 — Error 이벤트 후 [DONE]으로 끝나야 한다."""
    server.app.state.deps = _BrokenDeps()
    try:
        text = _client().get("/chat/stream", params={"message": "안녕"}).text
    finally:
        del server.app.state.deps
    assert '"type": "Error"' in text and '"ok": false' in text
    assert "session db unavailable" in text
    assert text.rstrip().endswith("data: [DONE]")
