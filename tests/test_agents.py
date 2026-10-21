"""Multi-Agent research — supervisor가 서브에이전트를 병렬로 호출하고, 실패를 에이전트 단위로 격리한다.

의존성 주입으로 가짜 LLM·MCP·retriever를 넣어 실제 서버 없이 재현한다.
"""
import asyncio
import time

from agent.deps import SupervisorDeps
from agent.fake_llm import FastLLM, QualityLLM
from agent.graph import build_graph
from tests.test_graph_fallback import FakeMCP


class FakeRetriever:
    """질의만 보면 판단이 애매하고(margin 0.002), alert까지 보면 확실해지는 retriever."""
    embedder = type("E", (), {"name": "fake"})()

    def __init__(self, delay: float = 0.0, margin: float = 0.05):
        self.delay, self.margin, self.calls = delay, margin, []

    def classify(self, query, collected):
        time.sleep(self.delay)
        with_alerts = any(c["source"] == "monitoring" for c in collected)
        self.calls.append(with_alerts)
        margin = 0.05 if with_alerts else self.margin
        return {"incident_type": "cpu-spike", "score": 0.7, "margin": margin,
                "ranking": [["cpu-spike", 0.7], ["high-latency", 0.7 - margin]], "embed_tokens": 3}


class SlowMCP(FakeMCP):
    async def call_tool(self, name, arguments, server="ops"):
        await asyncio.sleep(0.5)
        return await super().call_tool(name, arguments, server)


class AnalyzingLLM(FastLLM):
    """비교 분석이 필요하다고 판단하는 fast LLM (복잡한 질문)."""

    def route(self, query):
        result, usage = super().route(query)
        return {**result, "needs_analysis": True}, usage

    def plan(self, query, procedure_prompt):
        result, usage = super().plan(query, procedure_prompt)
        return {**result, "needs_analysis": True}, usage


def _run(query, fast=None, mcp=None, retriever=None):
    deps = SupervisorDeps(fast_llm=fast or FastLLM("fake", 0.0), quality_llm=QualityLLM("fake", 0.0),
                          mcp=mcp or FakeMCP(), session_store=None, version="v2", retriever=retriever)
    return asyncio.run(build_graph(deps).ainvoke(
        {"query": query, "thread_id": "t", "history": [], "events": [], "cost_usd": 0.0}))


def _agents(result, event_type="AgentCompleted"):
    return [e["agent"] for e in result["events"] if e["type"] == event_type]


def test_monitoring_and_runbook_agents_run_in_parallel():
    """모니터링(0.35+0.5초)과 runbook(0.5초)이 동시에 돌면 research 단계는 합보다 짧다."""
    result = _run("payments-service 장애 진단", mcp=SlowMCP(), retriever=FakeRetriever(delay=0.5))
    assert set(_agents(result)) == {"monitoring", "runbook"}
    assert result["parallel_elapsed"] < 1.2   # 순차라면 0.85 + 0.5 = 1.35초 이상
    sources = {c["source"] for c in result["collected"]}
    assert {"monitoring", "runbook"} <= sources


def test_uncertain_runbook_is_searched_again_with_alerts():
    """1차(질의만)의 1·2위 차가 작으면 replan_check가 alert를 더해 runbook만 1회 재검색한다."""
    retriever = FakeRetriever(margin=0.002)
    result = _run("payments-service 장애 진단", retriever=retriever)
    assert retriever.calls == [False, True]          # 1차는 질의만, 재검색은 alert 포함
    assert _agents(result) == ["monitoring", "runbook", "runbook"]
    replan = [e for e in result["events"] if e["type"] == "ReplanCheck"]
    assert [e["is_sufficient"] for e in replan] == [False, True]   # 상한 1회
    assert sum(1 for c in result["collected"] if c["source"] == "runbook") == 1


def test_confident_runbook_is_not_searched_again():
    retriever = FakeRetriever(margin=0.05)
    result = _run("payments-service 장애 진단", retriever=retriever)
    assert retriever.calls == [False]
    assert result.get("replan_rounds", 0) == 0


def test_simple_query_skips_the_analysis_agent():
    """LLM이 분석이 필요하다고 해도 시스템이 1개면 gate가 분석 에이전트를 빼낸다."""
    result = _run("payments-service 장애 진단", fast=AnalyzingLLM("fake", 0.0))
    gate = next(e for e in result["events"] if e["type"] == "GateApplied")
    assert gate["complex"] is False
    assert "analysis" not in _agents(result)


def test_complex_query_calls_the_analysis_agent():
    result = _run("payments-service랑 cache-service 공통 원인 장애 진단",
                  fast=AnalyzingLLM("fake", 0.0), retriever=FakeRetriever())
    gate = next(e for e in result["events"] if e["type"] == "GateApplied")
    assert gate["complex"] is True and gate["systems"] == 2
    assert _agents(result) == ["monitoring", "runbook", "analysis"]
    assert any(c["source"] == "analysis" for c in result["collected"])


def test_one_failed_system_does_not_drop_the_others():
    """모니터링 대상 하나의 조회만 실패하면 그 시스템만 빠지고 나머지로 답한다."""
    class HalfDownMCP(FakeMCP):
        async def call_tool(self, name, arguments, server="ops"):
            if arguments["system_name"] == "cache-service":
                raise ConnectionError("MCP 연결 실패")
            return await super().call_tool(name, arguments, server)

    result = _run("payments-service랑 cache-service 장애 진단", mcp=HalfDownMCP())
    done = [e["target"] for e in result["events"]
            if e["type"] == "TaskCompleted" and e["source"] == "monitoring"]
    failed = [e["target"] for e in result["events"] if e["type"] == "TaskFailed"]
    assert done == ["payments-service"] and failed == ["cache-service"]
    assert [d["stage"] for d in result["degraded"]] == ["mcp"]
    notices = [c["data"] for c in result["collected"] if c["source"] == "notice"]
    assert notices == ["cache-service 모니터링 상태를 조회하지 못했습니다 (MCP 호출 실패)"]
    assert "payments-service" in result["final"]


def test_two_systems_without_comparison_words_stay_simple():
    """시스템이 2개여도 비교를 요청하지 않으면(타임아웃 문의) 분석 에이전트를 부르지 않는다."""
    result = _run("gateway-service에서 payments-service로 가는 요청 장애",
                  fast=AnalyzingLLM("fake", 0.0), retriever=FakeRetriever())
    gate = next(e for e in result["events"] if e["type"] == "GateApplied")
    assert gate["complex"] is False and gate["llm_needs_analysis"] is True
    assert "analysis" not in _agents(result)


def test_comparison_request_calls_analysis_even_if_llm_says_no():
    result = _run("payments-service랑 cache-service 장애 공통 원인 진단", retriever=FakeRetriever())
    assert _agents(result)[-1] == "analysis"
