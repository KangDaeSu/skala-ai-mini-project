"""Research 전문 서브에이전트 — 각자 compiled subgraph이고, graph.py의 supervisor가 호출한다.

- monitoring: 조사 대상 시스템의 현재 상태 (MCP Tool)
- runbook   : 증상에 맞는 대응 절차 (RAG로 장애 유형 선택 → MCP Resource로 본문 조회)
- analysis  : 여러 시스템 결과의 공통 원인 비교 (LLM)

baseline은 research 노드 하나가 모니터링과 runbook 조회를 함께 했고, runbook은 조사가 끝난 뒤
alert 키워드로 골랐다. 에이전트는 외부 호출 실패를 예외로 던지지 않고 결과의 errors에 담아
돌려준다 — 한 에이전트·한 대상이 실패해도 나머지 결과로 답변을 만들 수 있게 하기 위함이다.
"""
from .analysis import build_analysis_agent
from .monitoring import build_monitoring_agent
from .runbook import build_runbook_agent


def build_agents(deps) -> dict:
    return {"monitoring": build_monitoring_agent(deps),
            "runbook": build_runbook_agent(deps),
            "analysis": build_analysis_agent(deps)}
