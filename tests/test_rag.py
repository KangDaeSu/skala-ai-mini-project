"""agent/rag.py — runbook 청크 분할, 임베딩 유사도 선택, 그래프 연동과 실패 시 폴백.

실제 임베딩 모델 대신 단어 포함 여부로 벡터를 만드는 가짜 임베더를 주입한다.
"""
import asyncio

import httpx

from agent.deps import SupervisorDeps
from agent.fake_llm import FastLLM, QualityLLM
from agent.graph import build_graph
from agent.rag import RunbookRetriever, split_runbook
from agent.errors import retry_sync
from tests.test_graph_fallback import FakeMCP

VOCAB = ["cpu", "메모리", "누수", "디스크", "타임아웃", "504", "지연", "느림", "db", "리플리케이션"]


class WordEmbedder:
    """텍스트에 VOCAB 단어가 몇 번 나오는지로 벡터를 만든다 — 결정론적인 가짜 임베딩."""
    name = "fake:words"

    def embed(self, texts, kind):
        return [[t.lower().count(w) + 0.01 for w in VOCAB] for t in texts], 0


class BrokenEmbedder:
    """임베딩 서버가 죽었다 — 실제 어댑터처럼 재시도(retry_sync)를 거쳐 실패한다."""
    name = "fake:broken"

    def embed(self, texts, kind):
        def down():
            raise httpx.ConnectError("embedding server down", request=httpx.Request("POST", "http://e"))
        return retry_sync(down)


def _retriever():
    return RunbookRetriever(WordEmbedder()).build()


def test_split_runbook_keeps_title_symptoms_and_steps():
    chunks = split_runbook("# Runbook: X\n\n> 증상: CPU 급증\n\n1. 첫째\n2. 둘째\n")
    assert chunks == ["Runbook: X\n증상: CPU 급증", "Runbook: X — 첫째", "Runbook: X — 둘째"]


def test_index_has_chunks_for_every_runbook():
    types = {c.incident_type for c in _retriever().chunks}
    assert types == {"cpu-spike", "memory-leak", "disk-full", "high-latency",
                     "network-timeout", "db-down"}


def test_user_symptom_wins_over_unrelated_alerts():
    """alert는 CPU인데 사용자는 DB 리플리케이션을 말한다 — 키워드 규칙은 cpu-spike를 골랐다."""
    collected = [{"source": "monitoring", "data": {"system_name": "payments-service",
                                                   "alerts": ["CPU 91% (threshold 80%)"]}}]
    found = _retriever().classify("DB 연결이 끊기고 리플리케이션이 멈췄어요", collected)
    assert found["incident_type"] == "db-down"
    assert found["ranking"][0][0] == "db-down" and found["margin"] > 0


def test_healthy_system_without_alerts_is_not_db_down():
    """baseline은 alert가 없으면 무조건 db-down이었다."""
    collected = [{"source": "monitoring", "data": {"system_name": "web-01", "alerts": []}}]
    assert _retriever().classify("메모리 누수가 의심돼요", collected)["incident_type"] == "memory-leak"


def _run_graph(retriever):
    deps = SupervisorDeps(fast_llm=FastLLM("fake", 0.0), quality_llm=QualityLLM("fake", 0.0),
                          mcp=FakeMCP(), session_store=None, version="v2", retriever=retriever)
    return asyncio.run(build_graph(deps).ainvoke(
        {"query": "web-01 디스크 장애 진단", "thread_id": "t", "history": [], "events": [],
         "cost_usd": 0.0}))


def test_graph_uses_rag_classifier():
    result = _run_graph(_retriever())
    replan = next(e for e in result["events"] if e["type"] == "ReplanCheck" and not e["is_sufficient"])
    assert replan["classifier"] == "rag" and replan["target"] == "disk-full"


def test_graph_falls_back_to_keyword_rules_when_embedding_fails():
    retriever = _retriever()
    retriever.embedder = BrokenEmbedder()   # 인덱스는 있는데 질의 임베딩이 실패하는 상황
    result = _run_graph(retriever)
    replan = next(e for e in result["events"] if e["type"] == "ReplanCheck" and not e["is_sufficient"])
    assert replan["classifier"] == "keyword"
    assert [d["stage"] for d in result["degraded"]] == ["rag"]
    assert result["degraded"][0]["error"]["kind"] == "ConnectError"
    assert result["final"]
