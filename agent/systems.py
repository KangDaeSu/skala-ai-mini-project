"""시스템명 처리 — 모니터링 대상 목록, 쿼리에서 시스템 추출, 조사 대상 보정.

baseline에는 같은 함수(_load_known_systems/_guess_target/_guess_targets)가 graph.py·
openai_llm.py·ollama_llm.py에 3벌 복사돼 있었고, 시스템을 못 찾으면 모두 "auth-service"로
폴백했다. 그 결과
- 모르는 시스템(billing-service)을 물어도 auth-service를 진단했고 (OpenAI 실측: 0/9)
- MCP Prompt에 "시스템: auth-service / 증상: billing-service…"라는 모순이 들어가
  Ollama 추론 모델이 thinking 루프에 빠졌다 (302초 후 HTTP 500)
- plan이 시스템을 일부만 뽑거나 언급하지 않은 시스템까지 뽑아도 보정되지 않았다

여기서는 "쿼리에 시스템이 명시돼 있으면 그 시스템들이 정답"이라는 규칙을 코드로 강제한다
(gate·replan과 같은 원칙: 실측으로 검증 가능한 결정은 모델이 아니라 코드가 내린다).
"""
import json
import re
from pathlib import Path

_MONITORING = Path(__file__).resolve().parent.parent / "data" / "monitoring.json"

# 시스템명처럼 생긴 토큰 (예: billing-service, order-api, web-01) — 모니터링 목록 밖 이름 감지용.
# 소문자로 시작하고 하이픈으로 이어지며 -service/-server/-api/-db/-숫자로 끝나는 단어.
_NAME_LIKE = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:service|server|api|db|\d+)\b")

UNKNOWN_LABEL = "미확인"


def load_known_systems() -> set[str]:
    """모니터링 대상 목록의 단일 출처 — data/monitoring.json의 키."""
    try:
        return set(json.loads(_MONITORING.read_text()).keys())
    except (OSError, json.JSONDecodeError):
        return set()


KNOWN_SYSTEMS = load_known_systems()


def mentioned(query: str) -> tuple[list[str], list[str]]:
    """쿼리에 등장한 (모니터링 대상 시스템, 모니터링 밖 시스템명)을 등장 순서대로 돌려준다."""
    # 쿼리에서 처음 등장한 위치로 정렬 — "gateway에서 payments로"는 [gateway, payments]
    known = [s for _, s in sorted((query.index(s), s) for s in KNOWN_SYSTEMS if s in query)]
    # 모니터링 목록에 없는 시스템명. 단 "payments-service-3"처럼 아는 시스템의 인스턴스명은
    # 모르는 시스템으로 치지 않는다(startswith 검사)
    unknown = [n for n in dict.fromkeys(_NAME_LIKE.findall(query))
               if n not in KNOWN_SYSTEMS and not any(n.startswith(k) for k in known)]
    return known, unknown


def prompt_label(query: str) -> str:
    """MCP Prompt의 '시스템:' 한 줄 — 쿼리에서 가장 먼저 등장한 시스템명(목록 밖이어도 그대로).
    없으면 "미확인". 증상 문장과 모순되는 이름을 넣지 않는 것이 목적이다."""
    known, unknown = mentioned(query)
    names = sorted((query.index(n), n) for n in known + unknown)
    return names[0][1] if names else UNKNOWN_LABEL


def resolve_targets(query: str, model_targets: list[str]) -> tuple[list[str], list[str]]:
    """조사 대상 보정 — (조사할 시스템, 모니터링 밖이라 조사할 수 없는 시스템명).

    1. 쿼리에 모니터링 대상 시스템이 있으면 정확히 그 시스템들만 조사한다
       (plan이 일부를 빠뜨리거나 언급 안 한 시스템을 더해도 쿼리가 우선)
    2. 언급된 시스템이 전부 모니터링 밖이면 아무것도 조사하지 않는다 (엉뚱한 시스템 진단 금지)
    3. 시스템 언급이 없으면 모델의 판단(예: "로그인" → auth-service) 중 유효한 것만 쓴다
    """
    known, unknown = mentioned(query)
    if known:
        return known, unknown
    if unknown:
        return [], unknown
    return [t for t in dict.fromkeys(model_targets) if t in KNOWN_SYSTEMS], []


def no_data_answer(notices: list[str]) -> str:
    """조사할 모니터링 데이터가 없을 때의 답변 — LLM에 맡기면 빈 번호 항목이나 지어낸 수치가
    나올 수 있어(실측: '2) 3)'이 빈 답변) 코드가 정해진 형식으로 만든다."""
    return "\n".join([
        f"1) {' / '.join(notices)}",
        f"2) 현재 모니터링 대상 시스템: {', '.join(sorted(KNOWN_SYSTEMS))}",
        "3) 위 목록의 시스템명으로 다시 요청해 주시면 상태 조회와 대응 절차를 안내하겠습니다.",
    ])


def notices_for(targets: list[str], unmonitored: list[str]) -> list[str]:
    """write 단계에 '참고' 사실로 넘길 안내 문구."""
    notes = [f"{n}은(는) 모니터링 대상 시스템이 아니어서 상태를 조회할 수 없습니다"
             for n in unmonitored]
    if not targets and not unmonitored:
        notes.append("요청에서 대상 시스템을 특정하지 못했습니다 — 시스템명을 알려주시면 조사하겠습니다")
    return notes
