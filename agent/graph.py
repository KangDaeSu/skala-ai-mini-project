"""v2 Supervisor — 실제 langgraph.StateGraph (Wave 4·5·6·7·8·10b·15 통합).

route → (chat 직행 | incident 파이프라인)
incident: plan(MCP Prompt 절차 반영) → gate(권위 게이트) → research(가드+병렬+재시도)
          → replan_check(부족 시 gap task 후 재조사) → analysis(needs_analysis=True일 때만
          실제 실행) → write → validate(반려 시 재작성) → finalize

모든 노드는 SupervisorDeps를 functools.partial로 주입받는 순수 함수다(Wave 13).
각 노드는 @traceable로 LangSmith에 계층 트리로 기록된다.

신뢰성 개선에서 바뀐 점 (그래프 구조·엣지는 그대로, 노드 내부만 변경):
- LLM을 부르는 노드(route·plan·analysis·write·chat_answer)는 호출이 끝내 실패해도 예외를
  밖으로 던지지 않고 fallback.py의 대체 동작으로 계속 진행한다 → _degrade()로 기록
  (baseline: 예외가 그래프 밖으로 터져 HTTP 500)
- plan: 모델이 고른 조사 대상을 systems.resolve_targets로 쿼리 기준 보정
- replan_check: runbook을 키워드 규칙 대신 RAG(rag.py)로 선택, 실패 시 키워드 규칙
- analysis·write: 조사한 모니터링 데이터가 없으면 LLM을 부르지 않는다
"""
import asyncio
import time
from functools import partial
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from langsmith import traceable

from .deps import SupervisorDeps
from .fallback import (CHAT_FALLBACK, degraded_event, describe, rule_route,
                       tag_current_run, template_answer)
from .retry import with_retry
from .systems import KNOWN_SYSTEMS, no_data_answer, notices_for, prompt_label, resolve_targets


class AgentState(TypedDict, total=False):
    query: str
    thread_id: str
    history: list[dict]
    route: str
    needs_analysis: bool
    tasks: list[dict]
    gate_removed: int
    collected: list[dict]
    replan_rounds: int
    retry_count: int
    parallel_elapsed: float
    draft: str
    validation_attempts: int
    validation_feedback: str
    final: str
    last_prompt: str
    cost_usd: float
    events: list[dict]
    degraded: list[dict]   # LLM 실패로 폴백한 단계 기록 (fallback.py)


def _cost(state: AgentState, usage: dict) -> float:
    return round(state.get("cost_usd", 0.0) + usage["usd"], 6)


def _degrade(state: AgentState, update: dict, stage: str, reason: str) -> dict:
    """폴백 기록 — Degraded 이벤트를 붙이고 degraded 목록에 누적, LangSmith 노드 run에 태그.

    update는 노드가 돌려줄 상태 델타다. events는 노드가 이미 새 목록을 만들었으면 그 뒤에,
    아니면 기존 state의 events 뒤에 붙인다. degraded 목록은 /chat metadata의
    degraded_count와 평가 스크립트의 degraded_runs 지표가 된다."""
    tag_current_run(stage, reason)
    event = degraded_event(stage, reason)
    update["events"] = update.get("events", state.get("events", [])) + [event]
    update["degraded"] = state.get("degraded", []) + [event]
    return update


def _rule_plan(query: str) -> dict:
    """plan 폴백 — LLM이 계획을 못 세우면 빈 계획에서 출발한다. 비어 있어도 괜찮은 이유:
    아래 plan_node의 resolve_targets가 쿼리에 명시된 시스템으로 조사 대상을 다시 채운다."""
    return {"needs_analysis": False, "tasks": []}


def _research_tasks(targets: list[str]) -> list[dict]:
    """보정된 조사 대상 목록 → research(monitoring) task 목록."""
    return [{"id": f"task-{i}", "agent": "research", "kind": "monitoring",
             "target": t, "status": "pending"} for i, t in enumerate(targets)]


@traceable(name="route_node")
async def route_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 5 — 모든 쿼리가 무거운 파이프라인을 탈 필요는 없다.

    LLM 호출이 실패하면(resilience의 재시도·예산을 다 쓴 뒤) 정규식 규칙으로 분류한다."""
    try:
        result, usage = deps.fast_llm.route(state["query"])
        reason = result.get("fallback")   # 어댑터 안에서 JSON 파싱 실패로 폴백한 경우
    except Exception as exc:
        result, usage = rule_route(state["query"], KNOWN_SYSTEMS), {"usd": 0.0}
        reason = f"LLM 호출 실패({describe(exc)}) → 규칙 기반 분류"
    event = {"type": "RouteDecided", "route": result["route"]}
    update = {"route": result["route"], "needs_analysis": result["needs_analysis"],
              "cost_usd": _cost(state, usage),
              "events": state.get("events", []) + [event]}
    return _degrade(state, update, "route", reason) if reason else update


@traceable(name="chat_answer_node")
async def chat_answer_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 5 direct 경로 — 히스토리 기반 응답 (Wave 12 세션 증명 지점).

    토큰 단위 스트리밍 — get_stream_writer()는 /chat/stream처럼 custom 모드로 소비될
    때만 실제로 전송되고, /chat(ainvoke)처럼 스트리밍하지 않는 호출에서는 자동으로
    no-op이 된다."""
    writer = get_stream_writer()
    reason = None
    try:
        reply, usage = await deps.fast_llm.chat(
            state["query"], state.get("history", []),
            on_token=lambda piece: writer({"type": "AnswerToken", "delta": piece}))
    except Exception as exc:
        reply, usage = CHAT_FALLBACK, {"usd": 0.0}
        reason = f"LLM 호출 실패({describe(exc)}) → 안내 문구로 대체"
    update = {"final": reply, "last_prompt": usage.get("prompt"),
              "cost_usd": _cost(state, usage),
              "events": state["events"] + [{"type": "Finalize", "pipeline": "chat-direct"}]}
    return _degrade(state, update, "chat", reason) if reason else update


@traceable(name="plan_node")
async def plan_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 4 — Plan/Task 분해. Wave 2의 MCP Prompt가 표준 절차를 깔아준다.

    resource와 마찬가지로 이름을 어느 서버가 들고 있는지 미리 가정하지 않고,
    find_prompt()로 연결된 서버들을 먼저 조회해 찾은 뒤에만 get_prompt를 보낸다."""
    prompt_server = await deps.mcp.find_prompt("incident_analysis_prompt")
    # system_name은 증상 문장과 모순되지 않는 이름만 넣는다(모르면 "미확인").
    # baseline은 billing-service 질의에 "시스템: auth-service"를 넣어 추론 모델이 thinking
    # 루프에 빠졌다(302초 후 HTTP 500의 직접 원인).
    procedure = await deps.mcp.get_prompt(
        "incident_analysis_prompt",
        {"system_name": prompt_label(state["query"]), "symptom": state["query"]},
        server=prompt_server,
    )
    try:
        result, usage = deps.fast_llm.plan(state["query"], procedure)
        reason = result.get("fallback")   # 어댑터 안에서 JSON 파싱 실패로 복구한 경우
    except Exception as exc:
        result, usage = _rule_plan(state["query"]), {"usd": 0.0}
        reason = f"LLM 호출 실패({describe(exc)}) → 쿼리의 시스템으로 계획"
    # 조사 대상 보정 — 쿼리에 명시된 시스템이 우선, 모니터링 밖 시스템은 조사하지 않는다
    model_targets = [t["target"] for t in result["tasks"]
                     if t["agent"] == "research" and t.get("target")]
    targets, unmonitored = resolve_targets(state["query"], model_targets)
    # research task는 보정된 대상으로 새로 만들고, analysis task는 모델 계획 그대로 둔다
    tasks = _research_tasks(targets) + [t for t in result["tasks"] if t["agent"] != "research"]
    events = list(state["events"])
    if targets != model_targets or unmonitored:
        events.append({"type": "TargetsCorrected", "model": model_targets,
                       "final": targets, "unmonitored": unmonitored})
    events.append({"type": "PlanCreated", "task_count": len(tasks), "targets": targets})
    # "모니터링 대상 아님" 같은 안내는 collected에 notice로 넣어 write 단계가 답변에 쓰게 한다
    notices = [{"source": "notice", "data": n} for n in notices_for(targets, unmonitored)]
    update = {"tasks": tasks, "needs_analysis": result["needs_analysis"],
              "collected": state.get("collected", []) + notices,
              "cost_usd": _cost(state, usage), "events": events}
    return _degrade(state, update, "plan", reason) if reason else update


@traceable(name="gate_node")
async def gate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 6 — 권위 게이트. needs_analysis=False인데 섞여 들어온 analysis task를
    프롬프트가 아니라 코드로 강제 제거한다."""
    tasks = state["tasks"]
    if not state.get("needs_analysis", False):
        kept = [t for t in tasks if t["agent"] != "analysis"]
        removed = len(tasks) - len(kept)
    else:
        kept, removed = tasks, 0
    event = {"type": "GateApplied", "removed_analysis_tasks": removed}
    return {"tasks": kept, "gate_removed": removed,
            "events": state["events"] + [event]}


@traceable(name="research_node")
async def research_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 15 가드 + Wave 10b 병렬 + Wave 9 재시도 + Wave 2 Tool/Resource 실호출."""
    tasks = state["tasks"]
    research_indices = [i for i, t in enumerate(tasks)
                        if t["agent"] == "research" and t["status"] == "pending"]
    # Wave 15 — 객체가 아니라 '실행할 목록'을 검사한다 (not research_agent 버그의 수정판)
    if not research_indices:
        return {"events": state["events"] +
                [{"type": "ResearchSkipped", "reason": "pending research task 0개"}]}

    retry_total = state.get("retry_count", 0)

    # URI를 코드에 하드코딩하지 않는다. 여러 MCP 서버가 연결돼 있고 그중 어느 서버가
    # "get_incident_runbook" resource를 제공하는지 모른다고 가정하고, 먼저 연결된
    # 서버들을 조회(list)해 유효한 서버를 찾은 뒤에만 그 서버로 요청한다.
    needs_runbook = any(tasks[i]["kind"] != "monitoring" for i in research_indices)
    runbook_server = runbook_uri_template = None
    if needs_runbook:
        runbook_server, runbook_uri_template = await deps.mcp.find_resource_template(
            "get_incident_runbook")

    async def run_one(idx: int) -> dict:
        task = tasks[idx]
        await asyncio.sleep(0.35)   # 태스크당 고정 지연 — 병렬 효과를 실측하기 위함
        if task["kind"] == "monitoring":
            data, retries = await with_retry(
                deps.mcp.call_tool, "get_monitoring_status",
                {"system_name": task["target"]})
            return {"idx": idx, "source": "monitoring", "data": data, "retries": retries}
        uri = runbook_uri_template.format(incident_type=task["target"])
        data = await deps.mcp.read_resource(uri, server=runbook_server)
        return {"idx": idx, "source": "runbook", "data": data, "retries": 0}

    started = time.perf_counter()
    results = await asyncio.gather(*(run_one(i) for i in research_indices))
    elapsed = round(time.perf_counter() - started, 2)

    new_tasks = [dict(t) for t in tasks]
    collected = list(state.get("collected", []))
    events = list(state["events"])
    for r in results:
        new_tasks[r["idx"]]["status"] = "done"
        collected.append({"source": r["source"], "data": r["data"]})
        retry_total += r["retries"]
        events.append({"type": "TaskCompleted", "id": new_tasks[r["idx"]]["id"],
                       "source": r["source"], "target": new_tasks[r["idx"]]["target"],
                       "retries": r["retries"]})
    return {"tasks": new_tasks, "collected": collected, "retry_count": retry_total,
            "parallel_elapsed": elapsed, "events": events}


# [baseline 규칙] RAG가 없거나(RUNBOOK_CLASSIFIER=keyword) 임베딩이 실패했을 때만 쓰인다.
# 사용자 질의를 보지 않고 alert 문구만, 목록 순서대로 매칭한다는 한계가 RAG 도입의 이유.
# 수집된 모니터링 결과(상태·알림 문구)를 보고 어떤 runbook이 맞는지 고른다. LLM에게
# 다시 묻는 대신 코드 레벨 규칙으로 판단한다 — gate(Wave 6)·replan(Wave 7)과 같은 설계
# 원칙: 모델의 판단을 그대로 믿지 않고, 실측 데이터로 검증 가능한 결정은 코드가 내린다.
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


def _classify_incident_type(collected: list[dict]) -> str:
    text = " ".join(
        f"{c['data'].get('status', '')} " + " ".join(c["data"].get("alerts", []))
        for c in collected if c.get("source") == "monitoring"
    ).lower()
    for keyword, incident_type in _INCIDENT_TYPE_RULES:
        if keyword in text:
            return incident_type
    return "db-down"   # 매칭되는 증상이 없으면 가장 일반적인 장애 대응 절차로 폴백


@traceable(name="replan_check_node")
async def replan_check_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 7 — 1차 수집 결과 평가. runbook이 없으면 gap task만 추가해 재조사.

    plan은 monitoring task만 만들기 때문에 1차 조사 뒤에는 거의 항상 runbook이 없다 —
    즉 runbook 선택은 사실상 이 노드가 전담한다(RAG 적용 지점)."""
    has_runbook = any(c["source"] == "runbook" for c in state.get("collected", []))
    has_monitoring = any(c["source"] == "monitoring" for c in state.get("collected", []))
    rounds = state.get("replan_rounds", 0)
    # 모니터링 데이터가 없으면(대상이 모니터링 밖이거나 특정 불가) 증상 근거가 없으므로
    # runbook을 추측하지 않는다 — baseline은 이때 db-down으로 폴백해 엉뚱한 절차를 안내했다
    if has_runbook or rounds >= 1 or not has_monitoring:
        verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": True}
        return {"events": state["events"] + [verdict]}
    collected = state.get("collected", [])
    incident_type, detail, update = None, {"classifier": "keyword"}, {}
    if deps.retriever is not None:   # RAG — 질의 + 수집된 alert의 임베딩 유사도로 runbook 선택
        try:
            found = deps.retriever.classify(state["query"], collected)
            incident_type = found["incident_type"]
            # 유사도·1·2위 차이를 이벤트에 남겨 웹 UI·평가에서 판단 근거를 볼 수 있게 한다
            detail = {"classifier": "rag", **{k: found[k] for k in
                                              ("score", "margin", "ranking", "embed_tokens")}}
        except Exception as exc:     # 임베딩 실패 시 baseline 키워드 규칙으로 폴백
            update = _degrade(state, {}, "rag", f"임베딩 실패({describe(exc)}) → 키워드 규칙")
    if incident_type is None:
        incident_type = _classify_incident_type(collected)
    gap_task = {"id": "task-gap-runbook", "agent": "research", "kind": "runbook",
                "target": incident_type, "status": "pending"}
    verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": False,
               "gap_task": gap_task["id"], "target": incident_type, **detail}
    # update는 RAG 실패 시의 Degraded 기록(events·degraded)이다 — 있으면 그 events 뒤에 verdict
    return {**update, "tasks": state["tasks"] + [gap_task], "replan_rounds": rounds + 1,
            "events": update.get("events", state["events"]) + [verdict]}


@traceable(name="analysis_node")
async def analysis_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 6 보완 — needs_analysis=True가 정당한 경우(모델의 자기모순이 아니라
    실제로 패턴 비교가 필요하다고 판단한 경우)를 위한 실행 경로. gate가 살려둔
    agent=='analysis' task가 있을 때만 수집된 monitoring 결과들을 비교 분석한다."""
    tasks = state["tasks"]
    pending = [t for t in tasks if t["agent"] == "analysis" and t["status"] == "pending"]
    if not pending:
        return {"events": state["events"] +
                [{"type": "AnalysisSkipped", "reason": "analysis task 0개"}]}
    if not any(c["source"] == "monitoring" for c in state.get("collected", [])):
        # 비교할 모니터링 데이터가 없으면 분석하지 않는다 ("특이 패턴 없음"이 답변에 섞이던 문제)
        return {"tasks": [{**t, "status": "done"} if t["agent"] == "analysis" else t for t in tasks],
                "events": state["events"] +
                [{"type": "AnalysisSkipped", "reason": "모니터링 데이터 없음"}]}
    new_tasks = [dict(t) for t in tasks]
    for t in new_tasks:
        if t["agent"] == "analysis" and t["status"] == "pending":
            t["status"] = "done"
    try:
        summary, usage = deps.fast_llm.analyze(state.get("collected", []))
    except Exception as exc:   # 비교 분석은 부가 단계 — 건너뛰고 수집된 사실로 답변을 쓴다
        update = {"tasks": new_tasks, "events": state["events"] +
                  [{"type": "AnalysisSkipped", "reason": "LLM 호출 실패"}]}
        return _degrade(state, update, "analyze", f"LLM 호출 실패({describe(exc)}) → 분석 생략")
    collected = state.get("collected", []) + [{"source": "analysis", "data": summary}]
    event = {"type": "AnalysisCompleted", "length": len(summary)}
    return {"tasks": new_tasks, "collected": collected,
            "cost_usd": _cost(state, usage), "events": state["events"] + [event]}


@traceable(name="write_node")
async def write_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 8/10a — 고품질 모델로 초안 작성 (1차는 의도적 저품질).

    토큰마다 attempt 번호를 같이 실어 보낸다 — validate가 반려해 재작성(attempt 증가)
    될 때 프론트가 새 말풍선으로 끊어서 보여줄 수 있게 하기 위함(Wave 8 재작성 루프를
    그대로 노출)."""
    attempt = state.get("validation_attempts", 0) + 1
    writer = get_stream_writer()
    collected = state.get("collected", [])
    if not any(c["source"] == "monitoring" for c in collected):
        # 조사한 시스템이 없으면(모니터링 대상 아님 / 대상 특정 불가) LLM 없이 안내 답변
        draft = no_data_answer([c["data"] for c in collected if c["source"] == "notice"]
                               or notices_for([], []))
        writer({"type": "AnswerToken", "attempt": attempt, "delta": draft})   # 웹 UI 스트리밍에도 전달
        return {"draft": draft, "events": state["events"] + [
            {"type": "DraftWritten", "attempt": attempt, "length": len(draft), "llm": False}]}
    reason = None
    try:
        draft, usage = await deps.quality_llm.write(
            state["query"], state.get("collected", []),
            attempt, state.get("validation_feedback"),
            on_token=lambda piece: writer(
                {"type": "AnswerToken", "attempt": attempt, "delta": piece}))
    except Exception as exc:   # LLM 없이 수집된 사실만으로 1) 2) 3) 답변을 만든다
        draft, usage = template_answer(state["query"], state.get("collected", [])), {"usd": 0.0}
        reason = f"LLM 호출 실패({describe(exc)}) → 수집된 사실로 템플릿 답변"
    update = {"draft": draft, "last_prompt": usage.get("prompt"),
              "cost_usd": _cost(state, usage),
              "events": state["events"] + [{"type": "DraftWritten", "attempt": attempt,
                                            "length": len(draft)}]}
    return _degrade(state, update, "write", reason) if reason else update


@traceable(name="validate_node")
async def validate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 8 — 코드 기준 검증: 30자 이상 + 절차 번호 포함이어야 합격."""
    draft = state["draft"]
    attempts = state.get("validation_attempts", 0) + 1
    ok = len(draft) >= 30 and "1)" in draft
    verdict = "합격" if ok else "불합격"
    if not ok and attempts >= 3:   # 실모델 무한 재작성 방지 — 최대 3회 후 통과 처리
        ok, verdict = True, "합격(최대 시도 도달 — 통과 처리)"
    feedback = None if ok else (
        f"응답이 너무 짧습니다({len(draft)}자, 최소 30자). 절차를 1) 2) 3) 번호로 "
        f"구체적으로 설명하세요.")
    event = {"type": "Validation", "attempt": attempts, "verdict": verdict}
    return {"validation_attempts": attempts, "validation_feedback": feedback,
            "events": state["events"] + [event]}


@traceable(name="finalize_node")
async def finalize_node(state: AgentState, deps: SupervisorDeps) -> dict:
    return {"final": state["draft"],
            "events": state["events"] + [{"type": "Finalize", "pipeline": "incident-v2"}]}


def _after_route(state: AgentState) -> str:
    return "chat_answer" if state["route"] == "chat" else "plan"


def _after_replan_check(state: AgentState) -> str:
    last = state["events"][-1]
    return "analysis" if last.get("is_sufficient") else "research"


def _after_validate(state: AgentState) -> str:
    return "finalize" if state.get("validation_feedback") is None else "write"


def build_graph(deps: SupervisorDeps):
    g = StateGraph(AgentState)
    node = lambda fn: partial(fn, deps=deps)   # Wave 13 — 명시적 의존성 주입
    g.add_node("route", node(route_node))
    g.add_node("chat_answer", node(chat_answer_node))
    g.add_node("plan", node(plan_node))
    g.add_node("gate", node(gate_node))
    g.add_node("research", node(research_node))
    g.add_node("replan_check", node(replan_check_node))
    g.add_node("analysis", node(analysis_node))
    g.add_node("write", node(write_node))
    g.add_node("validate", node(validate_node))
    g.add_node("finalize", node(finalize_node))

    g.set_entry_point("route")
    g.add_conditional_edges("route", _after_route,
                            {"chat_answer": "chat_answer", "plan": "plan"})
    g.add_edge("chat_answer", END)
    g.add_edge("plan", "gate")
    g.add_edge("gate", "research")
    g.add_edge("research", "replan_check")
    g.add_conditional_edges("replan_check", _after_replan_check,
                            {"analysis": "analysis", "research": "research"})
    g.add_edge("analysis", "write")
    g.add_edge("write", "validate")
    g.add_conditional_edges("validate", _after_validate,
                            {"finalize": "finalize", "write": "write"})
    g.add_edge("finalize", END)
    return g.compile()
