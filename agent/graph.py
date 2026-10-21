"""v2 Supervisor — 실제 langgraph.StateGraph. research 구간을 전문 서브에이전트로 나눴다.

route → (chat 직행 | incident 파이프라인)
incident: plan(MCP Prompt 절차 + 조사 대상 보정) → gate(분석 필요 여부를 코드로 확정)
          → research(supervisor: monitoring ∥ runbook 에이전트 병렬 호출)
          → replan_check(runbook 선택이 불확실하면 alert를 더해 1회 재검색)
          → analysis(분석 에이전트, 복잡한 질문만) → write → validate(반려 시 재작성) → finalize

모든 노드는 SupervisorDeps를 functools.partial로 주입받는 순수 함수다(Wave 13).
각 노드·에이전트는 @traceable로 LangSmith에 계층 트리로 기록된다.

baseline 대비 바뀐 점:
- research: 노드 하나가 모니터링·runbook 조회를 함께 하던 것을 서브에이전트(agents/)로 분리하고,
  runbook을 조사 뒤 키워드로 고르던 것을 runbook 에이전트가 처음부터 RAG로 병렬 검색한다
- replan_check: "runbook이 없으면 재조사"에서 "runbook 선택이 불확실하면 재검색"으로 (상한 1회)
- plan: 모르는 시스템을 auth-service로 바꾸던 하드코딩 대신 쿼리에 명시된 시스템만 조사한다
- 외부 호출은 timeout + 일시 오류 재시도(errors.py)를 거치고, 그래도 실패하면 노드가
  try/except EXTERNAL로 잡아 대체 동작으로 진행한다 (baseline: 예외가 그래프 밖으로 터져 HTTP 500)
"""
import asyncio
import os
import re
import time
from functools import partial
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from langsmith import traceable

from .agents import build_agents
from .deps import SupervisorDeps
from .errors import EXTERNAL, call_mcp, describe, error_info
from .fallback import (CHAT_FALLBACK, DEFAULT_PROCEDURE, degraded_event, rule_route,
                       tag_current_run, template_answer)
from .systems import KNOWN_SYSTEMS, no_data_answer, notices_for, prompt_label, resolve_targets

# runbook 선택의 1·2위 유사도 차가 이보다 작으면 "불확실" — alert를 더해 한 번 더 검색한다.
# 기준값 근거(OpenAI 실측): 틀린 선택은 차이가 0.003, 맞힌 선택은 모두 0.01 이상이었다.
RAG_MIN_MARGIN = float(os.environ.get("RAG_MIN_MARGIN", 0.01))

# 비교 분석을 요청하는 표현 — "같이 확인해줘"처럼 함께 조회만 하라는 표현은 넣지 않는다
_COMPARE_PATTERN = re.compile(r"공통|비교|둘 다|동시에|연관|상관|패턴")


class AgentState(TypedDict, total=False):
    query: str
    thread_id: str
    history: list[dict]
    route: str
    needs_analysis: bool
    tasks: list[dict]
    gate_removed: int
    collected: list[dict]
    runbook_round: int | None   # 실행할 runbook 검색 차수 (0: 1차, 1: 재검색, None: 없음)
    runbook_detail: dict        # 마지막 runbook 선택 근거 (RAG 유사도·1·2위 차)
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
    degraded: list[dict]   # 외부 호출 실패로 폴백한 단계 기록 (fallback.py)


def _cost(state: AgentState, usage: dict) -> float:
    return round(state.get("cost_usd", 0.0) + usage["usd"], 6)


def _degrade(state: AgentState, update: dict, stage: str, reason: str,
             error: dict | None = None) -> dict:
    """폴백 기록 — Degraded 이벤트를 붙이고 degraded 목록에 누적, LangSmith 노드 run에 태그.

    update는 노드가 돌려줄 상태 델타다. events·degraded는 노드가 이미 새 목록을 만들었으면
    (같은 노드에서 두 번 폴백한 경우 등) 그 뒤에, 아니면 기존 state 뒤에 붙인다."""
    tag_current_run(stage, reason)
    event = degraded_event(stage, reason, error)
    update["events"] = update.get("events", state.get("events", [])) + [event]
    update["degraded"] = update.get("degraded", state.get("degraded", [])) + [event]
    return update


def _research_tasks(targets: list[str]) -> list[dict]:
    """보정된 조사 대상 목록 → research(monitoring) task 목록."""
    return [{"id": f"task-{i}", "agent": "research", "kind": "monitoring",
             "target": t, "status": "pending"} for i, t in enumerate(targets)]


@traceable(name="route_node")
async def route_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 5 — 모든 쿼리가 무거운 파이프라인을 탈 필요는 없다.

    LLM 호출이 재시도까지 실패하면 정규식 규칙으로 분류한다."""
    error = None
    try:
        # 동기 HTTP 호출이라 스레드에서 돌려 이벤트 루프(다른 요청)를 막지 않는다
        result, usage = await asyncio.to_thread(deps.fast_llm.route, state["query"])
        reason = result.get("fallback")   # 어댑터 안에서 JSON 파싱 실패로 폴백한 경우
    except EXTERNAL as exc:
        result, usage, error = rule_route(state["query"], KNOWN_SYSTEMS), {"usd": 0.0}, error_info(exc)
        reason = f"LLM 호출 실패({describe(exc)}) → 규칙 기반 분류"
    event = {"type": "RouteDecided", "route": result["route"]}
    update = {"route": result["route"], "needs_analysis": result["needs_analysis"],
              "cost_usd": _cost(state, usage),
              "events": state.get("events", []) + [event]}
    return _degrade(state, update, "route", reason, error) if reason else update


@traceable(name="chat_answer_node")
async def chat_answer_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 5 direct 경로 — 히스토리 기반 응답 (Wave 12 세션 증명 지점).

    토큰 단위 스트리밍 — get_stream_writer()는 /chat/stream처럼 custom 모드로 소비될
    때만 실제로 전송되고, /chat(ainvoke)처럼 스트리밍하지 않는 호출에서는 자동으로
    no-op이 된다."""
    writer = get_stream_writer()
    error = None
    try:
        reply, usage = await deps.fast_llm.chat(
            state["query"], state.get("history", []),
            on_token=lambda piece: writer({"type": "AnswerToken", "delta": piece}))
    except EXTERNAL as exc:
        reply, usage, error = CHAT_FALLBACK, {"usd": 0.0}, exc
    update = {"final": reply, "last_prompt": usage.get("prompt"),
              "cost_usd": _cost(state, usage),
              "events": state["events"] + [{"type": "Finalize", "pipeline": "chat-direct"}]}
    if error is None:
        return update
    return _degrade(state, update, "chat", f"LLM 호출 실패({describe(error)}) → 안내 문구로 대체",
                    error_info(error))


@traceable(name="plan_node")
async def plan_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 4 — Plan/Task 분해. Wave 2의 MCP Prompt가 표준 절차를 깔아준다.

    prompt 이름을 어느 서버가 들고 있는지 미리 가정하지 않고, find_prompt()로 연결된 서버들을
    먼저 조회해 찾은 뒤에만 get_prompt를 보낸다. MCP가 실패하면 같은 내용의 기본 절차로 계획한다."""
    update: dict = {}
    try:
        server, _ = await call_mcp(deps.mcp.find_prompt, "incident_analysis_prompt")
        # system_name은 증상 문장과 모순되지 않는 이름만 넣는다(모르면 "미확인").
        # baseline은 billing-service 질의에 "시스템: auth-service"를 넣어 추론 모델이 thinking
        # 루프에 빠졌다(302초 후 HTTP 500의 직접 원인).
        procedure, _ = await call_mcp(
            deps.mcp.get_prompt, "incident_analysis_prompt",
            {"system_name": prompt_label(state["query"]), "symptom": state["query"]},
            server=server)
    except EXTERNAL as exc:
        procedure = DEFAULT_PROCEDURE + f"\n## 증상\n{state['query']}\n"
        update = _degrade(state, update, "mcp",
                          f"MCP Prompt 조회 실패({describe(exc)}) → 기본 절차 사용", error_info(exc))

    error = None
    try:
        result, usage = await asyncio.to_thread(deps.fast_llm.plan, state["query"], procedure)
        reason = result.get("fallback")   # 어댑터 안에서 JSON 파싱 실패로 복구한 경우
    except EXTERNAL as exc:
        # LLM이 계획을 못 세우면 빈 계획에서 출발한다 — 아래 resolve_targets가 쿼리에
        # 명시된 시스템으로 조사 대상을 다시 채운다
        result, usage, error = {"needs_analysis": False, "tasks": []}, {"usd": 0.0}, error_info(exc)
        reason = f"LLM 호출 실패({describe(exc)}) → 쿼리의 시스템으로 계획"
    # 조사 대상 보정 — 쿼리에 명시된 시스템이 우선, 모니터링 밖 시스템은 조사하지 않는다
    model_targets = [t["target"] for t in result["tasks"]
                     if t["agent"] == "research" and t.get("target")]
    targets, unmonitored = resolve_targets(state["query"], model_targets)
    # research task는 보정된 대상으로 새로 만들고, analysis task는 모델 계획 그대로 둔다
    tasks = _research_tasks(targets) + [t for t in result["tasks"] if t["agent"] != "research"]
    events = list(update.get("events", state["events"]))
    if targets != model_targets or unmonitored:
        events.append({"type": "TargetsCorrected", "model": model_targets,
                       "final": targets, "unmonitored": unmonitored})
    events.append({"type": "PlanCreated", "task_count": len(tasks), "targets": targets})
    # "모니터링 대상 아님" 같은 안내는 collected에 notice로 넣어 write 단계가 답변에 쓰게 한다
    notices = [{"source": "notice", "data": n} for n in notices_for(targets, unmonitored)]
    update.update({"tasks": tasks, "needs_analysis": result["needs_analysis"],
                   "collected": state.get("collected", []) + notices,
                   # 조사할 시스템이 있을 때만 runbook을 찾는다 (없으면 증상 근거가 없다)
                   "runbook_round": 0 if targets else None,
                   "cost_usd": _cost(state, usage), "events": events})
    return _degrade(state, update, "plan", reason, error) if reason else update


@traceable(name="gate_node")
async def gate_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 6 — 권위 게이트: 분석 에이전트를 부를지 프롬프트가 아니라 코드로 확정한다.

    복잡한 질문 = 조사할 시스템이 2개 이상이고, 질문에 비교 표현(공통·비교·둘 다 …)이 있을 때.
    LLM의 needs_analysis는 참고로만 기록한다 — 소형 모델은 단순 질문에도 True를 자주 냈다(실측).
    (단순 질문 → monitoring·runbook 에이전트만 / 복잡한 질문 → + analysis 에이전트)"""
    tasks = state["tasks"]
    systems = sum(1 for t in tasks if t["agent"] == "research")
    complex_query = systems >= 2 and bool(_COMPARE_PATTERN.search(state["query"]))
    if complex_query and not any(t["agent"] == "analysis" for t in tasks):
        tasks = tasks + [{"id": "task-analysis", "agent": "analysis",
                          "kind": "pattern-analysis", "status": "pending"}]
    kept = tasks if complex_query else [t for t in tasks if t["agent"] != "analysis"]
    removed = len(tasks) - len(kept)
    event = {"type": "GateApplied", "removed_analysis_tasks": removed, "complex": complex_query,
             "systems": systems, "llm_needs_analysis": state.get("needs_analysis", False)}
    return {"tasks": kept, "gate_removed": removed, "events": state["events"] + [event]}


async def _call_agent(name: str, agent, inputs: dict, writer) -> tuple[dict, float]:
    """에이전트 1개 호출 — 시작을 화면에 즉시 알리고(custom 이벤트), 걸린 시간을 잰다."""
    writer({"type": "AgentStarted", "agent": name})
    started = time.perf_counter()
    output = await agent.ainvoke(inputs)
    return output, round(time.perf_counter() - started, 2)


@traceable(name="research_node")
async def research_node(state: AgentState, deps: SupervisorDeps, agents: dict) -> dict:
    """Supervisor — 전문 에이전트를 호출해 조사 결과를 모은다.

    1차: monitoring 에이전트(대상 시스템 상태) ∥ runbook 에이전트(질의로 RAG 검색)를 병렬 호출.
    재검색: replan_check가 요청하면 runbook 에이전트만 수집된 alert까지 넣어 다시 호출.
    에이전트는 외부 호출 실패를 errors로 돌려주므로, 여기서 예외가 나면 우리 코드의 버그다."""
    writer = get_stream_writer()
    tasks = [dict(t) for t in state["tasks"]]
    collected = list(state.get("collected", []))
    pending = [t for t in tasks if t["kind"] == "monitoring" and t["status"] == "pending"]
    runbook_round = state.get("runbook_round")

    calls = {}
    if pending:
        calls["monitoring"] = (agents["monitoring"], {"targets": [t["target"] for t in pending]})
    if runbook_round is not None:
        # 1차는 모니터링과 동시에 돌기 때문에 질의만, 재검색은 수집된 alert까지 본다
        calls["runbook"] = (agents["runbook"],
                            {"query": state["query"],
                             "collected": collected if runbook_round > 0 else []})
    if not calls:
        return {"events": state["events"] +
                [{"type": "ResearchSkipped", "reason": "조사할 시스템 없음"}]}

    started = time.perf_counter()
    outputs = await asyncio.gather(*(_call_agent(name, agent, inputs, writer)
                                     for name, (agent, inputs) in calls.items()))
    elapsed = round(time.perf_counter() - started, 2)
    results = dict(zip(calls, outputs))

    update: dict = {"events": list(state["events"]), "runbook_round": None}
    retry_total = state.get("retry_count", 0)
    errors: list[dict] = []
    for name, (_, agent_elapsed) in results.items():
        update["events"].append({"type": "AgentCompleted", "agent": name, "elapsed": agent_elapsed})

    if "monitoring" in results:
        by_target = {r["target"]: r for r in results["monitoring"][0]["results"]}
        for task in pending:   # pending은 tasks 안의 dict를 가리키므로 상태가 그대로 반영된다
            r = by_target[task["target"]]
            if "data" in r:
                task["status"] = "done"
                collected.append({"source": "monitoring", "data": r["data"]})
                retry_total += r["retries"]
                update["events"].append({"type": "TaskCompleted", "id": task["id"],
                                         "source": "monitoring", "target": task["target"],
                                         "retries": r["retries"]})
            else:   # 이 시스템만 실패 — 수치를 지어내지 않도록 "조회하지 못했다"는 사실을 남긴다
                task["status"] = "failed"
                what = f"{task['target']} 모니터링 상태"
                collected.append({"source": "notice",
                                  "data": f"{what}를 조회하지 못했습니다 (MCP 호출 실패)"})
                update["events"].append({"type": "TaskFailed", "id": task["id"],
                                         "source": "monitoring", "target": task["target"],
                                         "error": r["error"]})
                errors.append({"stage": "mcp", "reason": f"{what} 조회 실패({r['reason']})",
                               "error": r["error"]})

    if "runbook" in results:
        out = results["runbook"][0]
        errors += out.get("errors", [])
        detail = out.get("detail", {})
        update["runbook_detail"] = detail
        if out.get("runbook"):
            # 재검색이면 이전 runbook을 새 결과로 바꾼다
            collected = [c for c in collected if c["source"] != "runbook"]
            collected.append({"source": "runbook", "data": out["runbook"]})
            tasks = [t for t in tasks if t["kind"] != "runbook"] + [
                {"id": "task-runbook", "agent": "research", "kind": "runbook",
                 "target": out["incident_type"], "status": "done"}]
            retry_total += out.get("retries", 0)
            update["events"].append({"type": "TaskCompleted", "id": "task-runbook",
                                     "source": "runbook", "target": out["incident_type"],
                                     "retries": out.get("retries", 0),
                                     "round": runbook_round, **detail})

    update.update({"tasks": tasks, "collected": collected, "retry_count": retry_total,
                   "parallel_elapsed": elapsed})
    for e in errors:
        update = _degrade(state, update, e["stage"], e["reason"], e["error"])
    return update


@traceable(name="replan_check_node")
async def replan_check_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 7 — 상한형 Replanning(최대 1회). 조사 결과가 충분한지 평가만 한다.

    baseline은 "runbook이 없으면 재조사"였다 — plan이 monitoring task만 만들어 거의 항상 재조사가
    일어났다. 지금은 runbook 에이전트가 처음부터 병렬로 찾으므로, 기준을 "runbook 선택에 확신이
    있는가"로 바꿨다. 불확실하면(1·2위 유사도 차 < RAG_MIN_MARGIN, 또는 runbook을 못 찾음)
    수집된 alert까지 넣어 runbook 에이전트만 한 번 더 호출한다."""
    collected = state.get("collected", [])
    rounds = state.get("replan_rounds", 0)
    has_monitoring = any(c["source"] == "monitoring" for c in collected)
    has_runbook = any(c["source"] == "runbook" for c in collected)
    detail = state.get("runbook_detail") or {}
    margin = detail.get("margin")
    uncertain = detail.get("classifier") == "rag" and margin is not None and margin < RAG_MIN_MARGIN
    # 모니터링 데이터가 없으면 증상 근거가 없으므로 runbook을 다시 찾지 않는다
    if rounds >= 1 or not has_monitoring or (has_runbook and not uncertain):
        verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": True}
        return {"events": state["events"] + [verdict]}
    reason = (f"runbook 선택 불확실(1·2위 차 {margin:.3f})" if has_runbook
              else "runbook을 찾지 못함")
    verdict = {"type": "ReplanCheck", "round": rounds, "is_sufficient": False,
               "reason": reason + " → 모니터링 alert를 더해 재검색"}
    return {"runbook_round": rounds + 1, "replan_rounds": rounds + 1,
            "events": state["events"] + [verdict]}


@traceable(name="analysis_node")
async def analysis_node(state: AgentState, deps: SupervisorDeps, agents: dict) -> dict:
    """gate가 남겨 둔 analysis task가 있을 때만 분석 에이전트를 호출한다 (복잡한 질문)."""
    tasks = state["tasks"]
    if not any(t["agent"] == "analysis" and t["status"] == "pending" for t in tasks):
        return {"events": state["events"] +
                [{"type": "AnalysisSkipped", "reason": "단순 질문 — 비교 분석 불필요"}]}
    new_tasks = [{**t, "status": "done"} if t["agent"] == "analysis" else t for t in tasks]
    collected = state.get("collected", [])
    if sum(1 for c in collected if c["source"] == "monitoring") < 2:
        # 조회에 실패해 비교할 시스템이 2개 미만이면 분석하지 않는다
        return {"tasks": new_tasks, "events": state["events"] +
                [{"type": "AnalysisSkipped", "reason": "비교할 모니터링 데이터 부족"}]}
    out, elapsed = await _call_agent("analysis", agents["analysis"], {"collected": collected},
                                     get_stream_writer())
    events = state["events"] + [{"type": "AgentCompleted", "agent": "analysis", "elapsed": elapsed}]
    update = {"tasks": new_tasks, "cost_usd": _cost(state, out["usage"]), "events": events}
    if out.get("summary") is None:
        update["events"] = events + [{"type": "AnalysisSkipped", "reason": "LLM 호출 실패"}]
        for e in out.get("errors", []):
            update = _degrade(state, update, e["stage"], e["reason"], e["error"])
        return update
    update["collected"] = collected + [{"source": "analysis", "data": out["summary"]}]
    update["events"] = events + [{"type": "AnalysisCompleted", "length": len(out["summary"])}]
    return update


@traceable(name="write_node")
async def write_node(state: AgentState, deps: SupervisorDeps) -> dict:
    """Wave 8/10a — 고품질 모델로 초안 작성.

    토큰마다 attempt 번호를 같이 실어 보낸다 — validate가 반려해 재작성(attempt 증가)
    될 때 프론트가 새 말풍선으로 끊어서 보여줄 수 있게 하기 위함(Wave 8 재작성 루프를
    그대로 노출)."""
    attempt = state.get("validation_attempts", 0) + 1
    writer = get_stream_writer()
    collected = state.get("collected", [])
    if not any(c["source"] == "monitoring" for c in collected):
        # 조사한 시스템이 없으면(모니터링 대상 아님 / 대상 특정 불가 / 조회 실패) LLM 없이 안내 답변
        draft = no_data_answer([c["data"] for c in collected if c["source"] == "notice"]
                               or notices_for([], []))
        writer({"type": "AnswerToken", "attempt": attempt, "delta": draft})   # 웹 UI 스트리밍에도 전달
        return {"draft": draft, "events": state["events"] + [
            {"type": "DraftWritten", "attempt": attempt, "length": len(draft), "llm": False}]}
    error = None
    try:
        draft, usage = await deps.quality_llm.write(
            state["query"], collected, attempt, state.get("validation_feedback"),
            on_token=lambda piece: writer(
                {"type": "AnswerToken", "attempt": attempt, "delta": piece}))
    except EXTERNAL as exc:   # LLM 없이 수집된 사실만으로 1) 2) 3) 답변을 만든다
        draft, usage, error = template_answer(state["query"], collected), {"usd": 0.0}, exc
    update = {"draft": draft, "last_prompt": usage.get("prompt"),
              "cost_usd": _cost(state, usage),
              "events": state["events"] + [{"type": "DraftWritten", "attempt": attempt,
                                            "length": len(draft)}]}
    if error is None:
        return update
    return _degrade(state, update, "write",
                    f"LLM 호출 실패({describe(error)}) → 수집된 사실로 템플릿 답변",
                    error_info(error))


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
    agents = build_agents(deps)   # 서브에이전트(compiled subgraph)는 그래프와 함께 1회만 만든다
    g = StateGraph(AgentState)
    node = lambda fn: partial(fn, deps=deps)   # Wave 13 — 명시적 의존성 주입
    g.add_node("route", node(route_node))
    g.add_node("chat_answer", node(chat_answer_node))
    g.add_node("plan", node(plan_node))
    g.add_node("gate", node(gate_node))
    g.add_node("research", partial(research_node, deps=deps, agents=agents))
    g.add_node("replan_check", node(replan_check_node))
    g.add_node("analysis", partial(analysis_node, deps=deps, agents=agents))
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
