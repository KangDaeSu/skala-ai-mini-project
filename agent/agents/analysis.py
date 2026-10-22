"""분석 에이전트 — 여러 시스템의 모니터링 결과를 비교해 공통 원인 패턴을 찾는다 (LLM).

서브그래프: compare (노드 1개)
gate가 "조사한 시스템이 2개 이상이고 질문에 비교 표현(공통·비교·둘 다 …)이 있는" 경우에만 호출된다.
LLM이 실패하면 분석을 건너뛴다 — 부가 단계라 답변은 수집된 사실만으로도 쓸 수 있다.
"""
import asyncio
from functools import partial
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langsmith import traceable

from ..errors import EXTERNAL, describe, error_info


class AnalysisState(TypedDict, total=False):
    """supervisor가 collected를 넣고, 비교 분석 요약(summary)을 돌려받는다."""
    collected: list[dict]
    summary: str | None
    usage: dict
    errors: list[dict]


@traceable(name="analysis.compare")
async def compare(state: AnalysisState, deps) -> dict:
    """fast LLM으로 여러 시스템의 모니터링 결과를 비교한다. 실패하면 summary=None과 errors."""
    try:
        summary, usage = await asyncio.to_thread(deps.fast_llm.analyze, state["collected"])
    except EXTERNAL as exc:
        error = {"stage": "analyze", "reason": f"LLM 호출 실패({describe(exc)}) → 분석 생략",
                 "error": error_info(exc)}
        return {"summary": None, "usage": {"usd": 0.0}, "errors": [error]}
    return {"summary": summary, "usage": usage}


def build_analysis_agent(deps):
    """compare 노드 하나짜리 서브그래프."""
    g = StateGraph(AnalysisState)
    g.add_node("compare", partial(compare, deps=deps))
    g.set_entry_point("compare")
    g.add_edge("compare", END)
    return g.compile()
