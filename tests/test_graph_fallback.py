"""그래프 전체 — 의존성 주입(SupervisorDeps)으로 가짜 LLM·MCP를 넣어 장애 상황을 재현한다.

실제 LLM·MCP 서버 없이, 노드 코드는 그대로 둔 채 deps만 갈아 끼운다 (Wave 13).
"""
import asyncio

import httpx

from agent.deps import SupervisorDeps
from agent.fake_llm import FastLLM, QualityLLM
from agent.fallback import CHAT_FALLBACK, DEGRADED_NOTICE
from agent.graph import build_graph

REQ = httpx.Request("POST", "http://llm.test")


class FakeMCP:
    """MCP 서버 대역 — 모니터링 조회·runbook·prompt를 고정값으로 돌려준다."""

    async def find_prompt(self, name):
        return "ops"

    async def get_prompt(self, name, arguments, server="ops"):
        return f"시스템: {arguments['system_name']} / 증상: {arguments['symptom']}"

    async def call_tool(self, name, arguments, server="ops"):
        return {"system_name": arguments["system_name"], "status": "degraded",
                "cpu_percent": 91.0, "memory_percent": 55.0, "alerts": ["CPU 91% (threshold 80%)"]}

    async def find_resource_template(self, name):
        return "ops", "runbook://incident-response/{incident_type}"

    async def read_resource(self, uri, server):
        return "# Runbook: CPU 급증 대응 절차\n\n1. 확인한다.\n2. 원인을 찾는다.\n3. 증설한다.\n"


class DeadLLM:
    """모든 호출이 타임아웃으로 실패하는 LLM — resilience가 포기한 뒤의 상황."""
    name = "dead-llm"

    def _fail(self, *args, **kwargs):
        raise httpx.ReadTimeout("simulated outage", request=REQ)

    route = plan = analyze = _fail

    async def chat(self, *args, **kwargs):
        self._fail()

    async def write(self, *args, **kwargs):
        self._fail()


def _run(fast, quality, query, history=None):
    deps = SupervisorDeps(fast_llm=fast, quality_llm=quality, mcp=FakeMCP(),
                          session_store=None, version="v2")
    return asyncio.run(build_graph(deps).ainvoke(
        {"query": query, "thread_id": "t", "history": history or [], "events": [], "cost_usd": 0.0}))


def _monitored(result):
    return [e["target"] for e in result["events"]
            if e["type"] == "TaskCompleted" and e["source"] == "monitoring"]


def test_incident_survives_total_llm_outage():
    """LLM이 전부 죽어도 예외 대신 수집된 사실로 만든 축소 답변이 나온다 (baseline: HTTP 500)."""
    result = _run(DeadLLM(), DeadLLM(), "payments-service CPU가 급증했어요")
    assert result["final"].startswith(DEGRADED_NOTICE)
    assert "1)" in result["final"] and "CPU 91.0%" in result["final"]
    assert [d["stage"] for d in result["degraded"]] == ["route", "plan", "write"]
    assert _monitored(result) == ["payments-service"]


def test_chat_survives_total_llm_outage():
    result = _run(DeadLLM(), DeadLLM(), "안녕하세요")
    assert result["final"] == CHAT_FALLBACK
    assert [d["stage"] for d in result["degraded"]] == ["route", "chat"]


def test_unmonitored_system_is_not_replaced_with_auth_service():
    result = _run(FastLLM("fake", 0.0), QualityLLM("fake", 0.0), "billing-service 응답이 지연돼요")
    corrected = next(e for e in result["events"] if e["type"] == "TargetsCorrected")
    assert corrected["unmonitored"] == ["billing-service"]
    assert _monitored(result) == []                       # 엉뚱한 시스템을 조사하지 않는다
    assert not any(c["source"] == "runbook" for c in result["collected"])   # runbook도 추측 안 함
    assert any(c["source"] == "notice" for c in result["collected"])
    assert result["final"].startswith("1) billing-service은(는) 모니터링 대상")   # LLM 없이 안내 답변
    assert "auth-service" in result["final"].splitlines()[1]                 # 2) 모니터링 대상 목록


def test_plan_targets_are_corrected_to_the_query():
    """fake plan은 언제나 web-01을 끼워 넣는다 — 쿼리에 없는 대상은 덜어내야 한다."""
    result = _run(FastLLM("fake", 0.0), QualityLLM("fake", 0.0),
                  "gateway-service에서 payments-service로 가는 요청 지연")
    assert _monitored(result) == ["gateway-service", "payments-service"]
    assert not result.get("degraded")
