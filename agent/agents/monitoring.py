"""모니터링 에이전트 — 조사 대상 시스템들의 현재 상태를 MCP Tool로 조회한다.

서브그래프: fetch(대상별 병렬 조회) → assess(저하된 시스템·알림 정리)
대상 하나가 실패해도 나머지 결과는 그대로 돌려준다 (실패한 대상은 error로 표시).
"""
import asyncio
from functools import partial
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langsmith import traceable

from ..errors import EXTERNAL, call_mcp, describe, error_info


class MonitoringState(TypedDict, total=False):
    targets: list[str]
    results: list[dict]          # 대상별 {"target", "data", "retries"} 또는 {"target", "error", "reason"}
    degraded_systems: list[str]  # 상태가 healthy가 아닌 시스템
    alert_count: int


@traceable(name="monitoring.fetch")
async def fetch(state: MonitoringState, deps) -> dict:
    async def one(target: str) -> dict:
        await asyncio.sleep(0.35)   # 대상당 고정 지연 — baseline research와 같은 조건 (병렬 효과 실측용)
        try:
            data, retries = await call_mcp(deps.mcp.call_tool, "get_monitoring_status",
                                           {"system_name": target})
        except EXTERNAL as exc:
            return {"target": target, "error": error_info(exc), "reason": describe(exc)}
        return {"target": target, "data": data, "retries": retries}

    return {"results": list(await asyncio.gather(*(one(t) for t in state["targets"])))}


@traceable(name="monitoring.assess")
async def assess(state: MonitoringState, deps) -> dict:
    found = [r["data"] for r in state["results"] if "data" in r]
    return {"degraded_systems": [d["system_name"] for d in found if d.get("status") != "healthy"],
            "alert_count": sum(len(d.get("alerts") or []) for d in found)}


def build_monitoring_agent(deps):
    g = StateGraph(MonitoringState)
    g.add_node("fetch", partial(fetch, deps=deps))
    g.add_node("assess", partial(assess, deps=deps))
    g.set_entry_point("fetch")
    g.add_edge("fetch", "assess")
    g.add_edge("assess", END)
    return g.compile()
