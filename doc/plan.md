# 진행 계획 — 운영 인시던트 대응 에이전트 신뢰성(Reliability) 개선

> 선택 과제: 1번 (Base AI Agent 기능 개선)
> 레포: https://github.com/KangDaeSu/skala-ai-mini-project

## 문제 정의

baseline을 Ollama(qwen3:0.6b / 8b)로 회귀 쿼리 10개에 돌린 결과(2026-10-20 실측):

- `billing-service 응답이 느려요` → **300초 대기 후 500 에러**
  - 원인: 모르는 시스템명이 `auth-service`로 하드코딩 폴백 → MCP Prompt에 "시스템: auth-service /
    증상: billing-service…"라는 모순 → 추론 모드 모델이 thinking 루프(4000토큰 중 답변 0자) →
    토큰 상한·추론 off·예외 처리가 모두 없어 timeout까지 대기 후 500
- 두 시스템을 언급한 쿼리(4·5·6번)에서 plan이 한 시스템만 조사 — 누락 복구는 "0개일 때만" 동작
- `web-01 CPU 급증` → healthy라 alert가 없어 키워드 분류가 **db-down** runbook으로 폴백
- 30자 + `"1)"`만 보는 validate가 할루시네이션("15GB 확보", "재시작 수행")을 첫 시도에 통과

## 개선 포인트 (스프레드시트 등록)

- LLM 호출 안정화 (추론 모드 off·토큰 상한·단계별 타임아웃·재시도)
- LLM 실패 시 폴백 응답 (500 에러 대신 축소 답변 반환)
- 시스템명 하드코딩 폴백 제거 및 조사 대상 누락 보충
- 평가 스크립트 구축 및 Before/After 실측 (성공률·지연·토큰)
- 장애 주입 단위 테스트 (의존성 주입 활용)

## 측정 원칙

- **공식 Before/After 수치는 OpenAI 백엔드**(fast=gpt-4o-mini, quality=gpt-4o)로 측정한다.
  개발 중 확인은 Ollama로만 한다(비용 0).
- 평가는 `eval/run_eval.py`가 서버 없이 그래프를 프로세스 안에서 직접 실행한다 —
  Before/After 코드에 똑같이 적용되고, 측정 때마다 서버를 재시작할 필요가 없다.
- 결과는 우선 `output/`에 저장한다.
- **정상 모드를 먼저** 측정하고, OpenAI에서 신뢰성 차이가 드러나지 않으면 **장애 주입 모드**
  (httpx 전송 계층 monkeypatch — 응답 없음/5xx/깨진 JSON)를 추가한다.

## 단계

| 단계 | 내용 | 파일 | 측정 | 상태 |
|---|---|---|---|---|
| 0 | 평가 스크립트 + 데이터셋 + 장애 주입기, Before 측정 | `eval/run_eval.py`, `eval/dataset.json`, `eval/chaos.py` | Before (OpenAI, 정상·장애 주입) | 완료 |
| 1 | `agent/resilience.py` — 단계별 타임아웃·재시도·전체 시간 예산, Ollama `think:false`·`num_predict` | `resilience.py`, `openai_llm.py`, `ollama_llm.py` | 최대 지연 | 완료 |
| 2 | 실패 시 폴백(route/plan/analyze/write) + `Degraded` 이벤트 + LangSmith 태그 | 각 어댑터 / `graph.py` | 성공률, 폴백 수 | 완료 |
| 3 | `agent/systems.py` — 중복 함수 통합, 모르는 시스템은 "미확인", 누락 시스템 보충 | `systems.py`, `graph.py`, 어댑터 | 대상 정확도 | 완료 |
| 4 | 장애 주입 단위 테스트 (가짜 deps 주입) | `tests/` | pytest | 완료 |
| 5 | RAG runbook 선택 — 청크 임베딩(incident_type 메타데이터) + 질의·alert 가중 유사도, runbook 증상 키워드 보강 | `rag.py`, `graph.py`, `data/runbooks` | runbook 정확도 | 완료 |
| 6 | OpenAI 최종 측정 (After), Before와 비교표 | `eval/compare.py` | After | 완료 |
| 7 | 루트 README, 결과 보고서, 발표 자료 | `README.md` | — | README 완료 |
| 8 | (OpenAI 측정 이후) 실패 구조화 `CallResult`/`ExternalCallError`, MCP 방어선·자동 재연결, 서킷 브레이커·Retry-After·지터, 서버 `{ok, error}` 응답 | `resilience.py`, `mcp_client.py`, `graph.py`, `server.py` | Ollama 장애 주입(LLM+MCP) | 완료 |

## Before 측정 결과 (OpenAI, 커밋 `253fb4c`)

| 지표 | 정상 모드 (48회) | 장애 주입 모드 (32회) |
|---|---|---|
| 성공률 | 100% | 41% |
| 장애를 맞은 실행의 성공률 | — | 14% (3/22) |
| 최대 지연 | 7.6초 | 122.8초 |
| 대상 정확도 | 74% (모르는 시스템 0/9) | — |

정상 모드에서는 신뢰성 차이가 드러나지 않아 장애 주입 모드를 추가했다. 자세한 내용은
[eval/README.md](../eval/README.md), 원본 결과는 `output/before_*`.

## 평가 지표

| 지표 | 정의 |
|---|---|
| 성공률 | 예외 없이 답변이 나온 비율 |
| route 정확도 | chat / incident 분류가 기대값과 같은 비율 |
| 대상 정확도 | 조사한 모니터링 대상 집합 == 기대 집합 (모르는 시스템은 조사하지 않아야 정답) |
| runbook 일치율 | 선택된 runbook이 허용 목록 안에 있는 비율 (참고용) |
| 지연시간 | p50 / p95 / 최대 (쿼리 1건 전체) |
| LLM 호출 수 / 토큰 | 호출 관찰 래퍼가 센 값 (OpenAI `usage.total_tokens`) |
| 재시도 / 검증 반려 | `retry_count`, `validation_attempts` |

## 예상 트레이드오프 (한계 장표 재료)

- 추론 off → 속도↑, plan 품질↓ 가능성 — 대상 정확도로 함께 확인
- 토큰 상한이 낮으면 JSON 잘림 → 파싱 실패 → 폴백 증가
- 재시도 → 성공률↑, 최악 지연·비용↑ → 전체 시간 예산으로 제한
- 폴백 답변은 서버가 죽지 않는 대신 품질이 낮음 → "축소 답변" 표시 필요
- runbook 오분류·할루시네이션은 이번 범위 밖 → 추가 개선(RAG, LLM-as-judge)
