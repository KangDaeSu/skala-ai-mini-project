"""agent/systems.py — 시스템 추출과 조사 대상 보정 규칙."""
import pytest

from agent.systems import KNOWN_SYSTEMS, UNKNOWN_LABEL, notices_for, prompt_label, resolve_targets


def test_known_systems_come_from_monitoring_data():
    assert {"auth-service", "payments-service", "web-01"} <= KNOWN_SYSTEMS


@pytest.mark.parametrize("query, model_targets, expected", [
    # 쿼리에 명시된 시스템이 우선 — 모델이 빠뜨린 시스템은 보충
    ("gateway-service에서 payments-service로 가는 요청이 타임아웃", ["gateway-service"],
     ["gateway-service", "payments-service"]),
    # 모델이 언급 안 된 시스템을 더해도 쿼리 기준으로 덜어낸다
    ("web-01 CPU 급증, auth-service 커넥션 풀도", ["web-01", "auth-service", "log-service"],
     ["web-01", "auth-service"]),
    # 모니터링 밖 시스템만 언급되면 아무것도 조사하지 않는다 (baseline: auth-service 진단)
    ("billing-service 응답이 느려요", ["auth-service"], []),
    # 시스템 언급이 없으면 모델 판단 중 유효한 것만
    ("로그인 응답이 느려요", ["auth-service", "no-such-system"], ["auth-service"]),
    ("전체적으로 느려요", [], []),
    # 인스턴스명(payments-service-3)은 상위 시스템으로 본다
    ("payments-service-3 인스턴스가 느려요", [], ["payments-service"]),
])
def test_resolve_targets(query, model_targets, expected):
    targets, _ = resolve_targets(query, model_targets)
    assert targets == expected


def test_unmonitored_names_are_reported():
    targets, unmonitored = resolve_targets("billing-service 응답이 느려요", [])
    assert (targets, unmonitored) == ([], ["billing-service"])
    assert "billing-service" in notices_for(targets, unmonitored)[0]


def test_prompt_label_never_contradicts_the_symptom():
    """MCP Prompt의 '시스템:' 줄에 증상과 다른 시스템을 넣지 않는다 (8번 쿼리 500 에러의 원인)."""
    assert prompt_label("billing-service 응답이 느려요") == "billing-service"
    assert prompt_label("gateway-service에서 payments-service로") == "gateway-service"
    assert prompt_label("로그인 응답이 느려요") == UNKNOWN_LABEL


def test_notice_when_no_target_can_be_found():
    assert "특정하지 못했습니다" in notices_for([], [])[0]
