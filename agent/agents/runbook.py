"""Runbook 에이전트 — 증상에 맞는 대응 절차(runbook)를 찾아 본문을 가져온다.

서브그래프: retrieve(RAG로 장애 유형 선택) → read(MCP Resource로 runbook 본문 조회)

1차 호출은 모니터링 에이전트와 병렬로 돌아 사용자 질의만 본다. supervisor의 replan_check가
선택이 불확실하다고 판단하면(1·2위 유사도 차가 작음) 수집된 alert까지 넣어 한 번 더 호출된다.
"""
import asyncio
from functools import partial
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langsmith import traceable

from ..errors import EXTERNAL, call_mcp, describe, error_info


class RunbookState(TypedDict, total=False):
    query: str
    collected: list[dict]     # 재검색 때만 — 수집된 모니터링 결과(alert)를 함께 본다
    incident_type: str | None
    detail: dict              # 선택 근거: classifier, score, margin, ranking, embed_tokens
    runbook: str | None
    retries: int
    errors: list[dict]        # 폴백 기록 [{"stage", "reason", "error"}]


# [baseline 규칙] RAG가 없거나(RUNBOOK_CLASSIFIER=keyword) 임베딩이 실패했을 때만 쓴다.
# alert 문구만 목록 순서대로 매칭한다 — 사용자 질의를 보지 않는다는 한계가 RAG 도입의 이유.
_INCIDENT_TYPE_RULES = [
    ("latency", "high-latency"),
    ("pool", "high-latency"),
    ("cpu", "cpu-spike"),
    ("memory", "memory-leak"),
    ("heap", "memory-leak"),
    ("timeout", "network-timeout"),
    ("network", "network-timeout"),
    ("disk", "disk-full"),
    ("down", "db-down"),
]


def keyword_incident_type(collected: list[dict]) -> str | None:
    """alert가 하나도 없으면 추측하지 않는다 (baseline은 이때 db-down으로 폴백했다)."""
    monitoring = [c["data"] for c in collected if c.get("source") == "monitoring"]
    if not monitoring:
        return None
    text = " ".join(f"{d.get('status', '')} " + " ".join(d.get("alerts", []))
                    for d in monitoring).lower()
    for keyword, incident_type in _INCIDENT_TYPE_RULES:
        if keyword in text:
            return incident_type
    return "db-down"


@traceable(name="runbook.retrieve")
async def retrieve(state: RunbookState, deps) -> dict:
    collected = state.get("collected", [])
    if deps.retriever is not None:
        try:
            found = await asyncio.to_thread(deps.retriever.classify, state["query"], collected)
            detail = {"classifier": "rag", **{k: found[k] for k in
                                              ("score", "margin", "ranking", "embed_tokens")}}
            return {"incident_type": found["incident_type"], "detail": detail}
        except EXTERNAL as exc:   # 임베딩 실패 → 아래 키워드 규칙으로
            error = {"stage": "rag", "reason": f"임베딩 실패({describe(exc)}) → 키워드 규칙",
                     "error": error_info(exc)}
            return {"incident_type": keyword_incident_type(collected),
                    "detail": {"classifier": "keyword"}, "errors": [error]}
    return {"incident_type": keyword_incident_type(collected), "detail": {"classifier": "keyword"}}


@traceable(name="runbook.read")
async def read(state: RunbookState, deps) -> dict:
    if state.get("incident_type") is None:   # 장애 유형을 정하지 못했다 — 본문 조회 없음
        return {"runbook": None, "retries": 0}
    try:
        # URI를 하드코딩하지 않는다 — 연결된 서버 중 runbook resource를 가진 서버를 먼저 찾는다
        (server, uri_template), r1 = await call_mcp(deps.mcp.find_resource_template,
                                                    "get_incident_runbook")
        text, r2 = await call_mcp(deps.mcp.read_resource,
                                  uri_template.format(incident_type=state["incident_type"]),
                                  server=server)
    except EXTERNAL as exc:
        error = {"stage": "mcp", "reason": f"'{state['incident_type']}' runbook 조회 실패"
                                           f"({describe(exc)})", "error": error_info(exc)}
        return {"runbook": None, "retries": 0, "errors": state.get("errors", []) + [error]}
    return {"runbook": text, "retries": r1 + r2}


def build_runbook_agent(deps):
    g = StateGraph(RunbookState)
    g.add_node("retrieve", partial(retrieve, deps=deps))
    g.add_node("read", partial(read, deps=deps))
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "read")
    g.add_edge("read", END)
    return g.compile()
