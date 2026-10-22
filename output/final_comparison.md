# 최종 Before / After 비교 (OpenAI)

- 모델: fast=`openai:gpt-4o-mini`, quality=`openai:gpt-4o`
- Before 커밋 `253fb4c` (runbook 선택: keyword) · After 커밋 정상 `0f4b46e` · 장애 주입 `d3c9cc5` (runbook 선택: `rag(openai:text-embedding-3-small)`)
- 정상 모드: 21건 × 3회 · 장애 주입: 16건 × 2회, `hang=0.15,error=0.10,badjson=0.10` seed=42 (Before와 동일)

## 1. 장애 주입 모드 — 신뢰성

| 지표 | Before | After |
|---|---|---|
| 주입된 장애 수 | 23 | 50 |
| 장애를 맞은 실행 수 | 22 | 22 |
| **성공률** | 13/32 (41%) | 32/32 (100%) |
| **장애를 맞은 실행의 성공률** | 3/22 (14%) | 22/22 (100%) |
| 대체 동작(규칙·템플릿)이 일어난 실행 | 0 | 10 |
| 지연 p50 (초, 성공한 실행) | 6.1 | 14.47 |
| **최대 지연 (초, 실패 포함)** | 122.84 | 45.48 |

## 2. 정상 모드 — 품질 (회귀 검사 포함)

| 지표 | Before | After |
|---|---|---|
| 성공률 | 63/63 (100%) | 63/63 (100%) |
| route 정확도 | 63/63 (100%) | 63/63 (100%) |
| **조사 대상 정확도** | 44/54 (81%) | 54/54 (100%) |
| └ 모니터링 밖 시스템 (unknown-system) | 0/9 (0%) | 9/9 (100%) |
| **runbook 선택 정확도** | 30/45 (67%) | 42/45 (93%) |
| └ 증상·alert가 엇갈리는 케이스 (runbook) | 3/15 (20%) | 15/15 (100%) |
| 지연 p50 (초) | 5.04 | 4.93 |
| 지연 p95 (초) | 6.83 | 6.67 |
| 지연 최대 (초) | 7.57 | 8.61 |
| 평균 LLM 호출 수 | 3.13 | 2.86 |
| 평균 LLM 토큰 | 1030.7 | 998.3 |
| 총 토큰 (LLM + 임베딩) | 64,934 | 64,586 |

## 3. 쿼리별 — 정상 모드 (마지막 반복 기준)

| id | Before 조사 대상 → runbook | After 조사 대상 → runbook | Before p50(s) | After p50(s) |
|---|---|---|---|---|
| r1 | payments-service → cpu-spike ✅ | payments-service → cpu-spike ✅ | 5.5 | 4.98 |
| r2 | cache-service → memory-leak ✅ | cache-service → memory-leak ✅ | 4.75 | 5.54 |
| r3 | log-service → disk-full ✅ | log-service → disk-full ✅ | 5.04 | 4.97 |
| r4 | gateway-service, payments-service, auth-service → high-latency ❌ | gateway-service, payments-service → network-timeout ✅ | 5.64 | 5.6 |
| r5 | web-01, auth-service → high-latency ✅ | web-01, auth-service → cpu-spike ✅ | 4.98 | 4.94 |
| r6 | payments-service, cache-service → cpu-spike ✅ | payments-service, cache-service → memory-leak ✅ | 6.09 | 6.11 |
| r7 | auth-service → high-latency ✅ | auth-service → high-latency ✅ | 5.16 | 4.9 |
| r8 | auth-service → high-latency ❌ | - → - ✅ | 4.58 | 2.0 |
| r9 | - → - | - → - | 1.72 | 1.65 |
| r10 | - → - | - → - | 1.69 | 1.69 |
| s1 | auth-service → high-latency ❌ | - → - ✅ | 4.44 | 2.23 |
| s2 | auth-service → high-latency ❌ | - → - ✅ | 5.29 | 2.03 |
| s3 | auth-service, payments-service, cache-service → high-latency ✅ | auth-service, payments-service, cache-service → network-timeout ❌ | 6.4 | 6.7 |
| s4 | gateway-service, log-service → network-timeout ✅ | gateway-service, log-service → disk-full ✅ | 6.39 | 6.41 |
| s5 | cache-service → memory-leak ✅ | cache-service → memory-leak ✅ | 4.81 | 5.81 |
| s6 | auth-service → high-latency | gateway-service, auth-service, cache-service, log-service, payments-service, web-01 → network-timeout | 4.83 | 5.56 |
| b1 | web-01 → db-down ❌ | web-01 → cpu-spike ✅ | 4.78 | 4.38 |
| b2 | web-01 → db-down ❌ | web-01 → memory-leak ✅ | 5.89 | 4.82 |
| b3 | payments-service → cpu-spike ❌ | payments-service → db-down ✅ | 5.26 | 4.22 |
| b4 | gateway-service → network-timeout ✅ | gateway-service → network-timeout ✅ | 5.51 | 5.47 |
| b5 | auth-service → high-latency ❌ | auth-service → disk-full ✅ | 5.16 | 4.33 |
