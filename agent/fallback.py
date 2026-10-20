"""LLM 실패 시 대체 동작(graceful degradation).

resilience가 재시도·시간 예산을 다 쓰고도 실패하면 baseline은 예외가 그래프 밖으로 터져
HTTP 500이 됐다. 여기서는 단계별로 LLM 없이도 할 수 있는 최소한의 동작을 정의한다 —
서버는 죽지 않고, 사용자는 "축소된 답변"이라는 표시와 함께 수집된 사실을 받는다.

폴백이 일어나면 그래프 상태의 degraded 목록과 Degraded 이벤트로 남기고, LangSmith run에
"degraded" 태그와 실패 원인을 메타데이터로 붙여 대시보드에서 필터로 모아볼 수 있게 한다.
"""
import re

from langsmith.run_helpers import get_current_run_tree

# baseline 정규식(장애|진단|다운|지연|급증|incident|티켓)은 "느려요"·"타임아웃"을 놓쳐
# 장애 질의를 chat으로 잘못 보냈다(장애 주입 측정에서 실측) — 운영 증상 표현을 보강한다.
_INCIDENT_PATTERN = re.compile(
    r"장애|진단|다운|지연|급증|느려|느리|느림|타임아웃|timeout|에러|오류|실패|알림|경고|저하|"
    r"부족|꽉|치솟|폭증|incident|티켓|cpu|메모리|디스크|힙|커넥션|응답",
    re.IGNORECASE)

DEGRADED_NOTICE = "⚠️ LLM 응답 실패로, 수집된 사실만으로 자동 작성한 축소 답변입니다."
CHAT_FALLBACK = "죄송합니다. 지금은 답변을 생성하지 못했습니다(LLM 응답 실패). 잠시 후 다시 시도해 주세요."


def rule_route(query: str, known_systems: set[str]) -> dict:
    """route 폴백 — 운영 증상 표현이나 알려진 시스템명이 있으면 incident."""
    incident = bool(_INCIDENT_PATTERN.search(query)) or any(s in query for s in known_systems)
    return {"route": "incident" if incident else "chat", "needs_analysis": False}


def describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:120]}"


def degraded_event(stage: str, reason: str) -> dict:
    return {"type": "Degraded", "stage": stage, "reason": reason}


def tag_current_run(stage: str, reason: str) -> None:
    """지금 실행 중인 LangSmith run(노드)에 degraded 태그와 원인을 붙인다.
    LangSmith에서 tag = degraded 로 필터하면 폴백이 일어난 실행만 모아볼 수 있다."""
    rt = get_current_run_tree()   # @traceable 노드 안에서 호출되므로 그 노드의 run (추적 off면 None)
    if rt is not None:
        rt.add_tags(["degraded", f"degraded:{stage}"])
        rt.add_metadata({"degraded_stage": stage, "degraded_reason": reason})


def tag_request_run(result: dict) -> None:
    """요청 루트 run(chat_request)에 폴백 횟수를 남긴다 — LangSmith에서 루트 기준 필터용."""
    rt = get_current_run_tree()
    degraded = result.get("degraded", [])
    if rt is not None and degraded:
        rt.add_tags(["degraded"])
        rt.add_metadata({"degraded_count": len(degraded),
                         "degraded_stages": [d["stage"] for d in degraded]})


def template_answer(query: str, collected: list[dict]) -> str:
    """write 폴백 — 수집된 모니터링 수치와 runbook 절차만으로 1) 2) 3) 형식 답변을 만든다.
    LLM이 지어낼 여지가 없으므로 수치는 수집값 그대로다."""
    # collected의 source별로 나눈다: monitoring(MCP Tool 결과) / runbook(MCP Resource 본문) /
    # notice(systems.py가 넣은 "모니터링 대상 아님" 같은 안내)
    mon = [c["data"] for c in collected if c["source"] == "monitoring"]
    runbooks = [c["data"] for c in collected if c["source"] == "runbook"]
    notices = [c["data"] for c in collected if c["source"] == "notice"]

    status = " / ".join(
        f"{d['system_name']} 상태={d['status']}, CPU {d['cpu_percent']}%, "
        f"메모리 {d['memory_percent']}%, 알림: {', '.join(d['alerts']) or '없음'}"
        for d in mon) or "수집된 모니터링 데이터 없음"
    lines = [DEGRADED_NOTICE, f"요청: {query}", f"1) 모니터링: {status}"]
    if runbooks:
        body = [l.strip() for l in runbooks[0].strip().splitlines() if l.strip()]
        title = body[0].lstrip("# ") if body else "runbook"
        # "1. ..." 형식의 절차 줄만 뽑아 앞의 3개를 → 로 잇는다 (증상 키워드 줄은 제외됨)
        steps = [m.group(1) for l in body[1:] if (m := re.match(r"^\d+\.\s+(.*)", l))]
        lines.append(f"2) 표준 절차({title}): " + (" → ".join(steps[:3]) or "runbook 본문 확인 필요"))
    else:
        lines.append("2) 해당하는 대응 절차(runbook)를 확인하지 못했습니다 — 담당자 확인이 필요합니다.")
    lines.append("3) 정상화 후 원인 분석과 재발 방지 대책을 문서화하세요.")
    lines += [f"참고: {n}" for n in notices]
    return "\n".join(lines)
