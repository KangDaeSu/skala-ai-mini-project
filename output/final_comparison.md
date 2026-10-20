# 최종 Before / After 비교 (OpenAI)

- 모델: fast=`openai:gpt-4o-mini`, quality=`openai:gpt-4o`
- Before 커밋 `253fb4c` (runbook 선택: keyword) · After 커밋 `f585c7b` (runbook 선택: `rag(openai:text-embedding-3-small)`)
- 정상 모드: 21건 × 3회 · 장애 주입: 16건 × 2회, `hang=0.15,error=0.10,badjson=0.10` seed=42 (Before와 동일)

## 1. 장애 주입 모드 — 신뢰성

| 지표 | Before | After |
|---|---|---|
| 주입된 장애 수 | 23 | 53 |
| 장애를 맞은 실행 수 | 22 | 23 |
| **성공률** | 13/32 (41%) | 32/32 (100%) |
| **장애를 맞은 실행의 성공률** | 3/22 (14%) | 23/23 (100%) |
| 폴백(축소 답변)이 일어난 실행 | 0 | 11 |
| 지연 p50 (초, 성공한 실행) | 6.1 | 24.41 |
| **최대 지연 (초, 실패 포함)** | 122.84 | 98.89 |

## 2. 정상 모드 — 품질 (회귀 검사 포함)

| 지표 | Before | After |
|---|---|---|
| 성공률 | 63/63 (100%) | 63/63 (100%) |
| route 정확도 | 63/63 (100%) | 63/63 (100%) |
| **조사 대상 정확도** | 44/54 (81%) | 54/54 (100%) |
| └ 모니터링 밖 시스템 (unknown-system) | 0/9 (0%) | 9/9 (100%) |
| **runbook 선택 정확도** | 30/45 (67%) | 42/45 (93%) |
| └ 증상·alert가 엇갈리는 케이스 (runbook) | 3/15 (20%) | 15/15 (100%) |
| 지연 p50 (초) | 5.04 | 5.68 |
| 지연 p95 (초) | 6.83 | 7.59 |
| 지연 최대 (초) | 7.57 | 8.73 |
| 평균 LLM 호출 수 | 3.13 | 3.19 |
| 평균 LLM 토큰 | 1030.7 | 1090.3 |
| 총 토큰 (LLM + 임베딩) | 64,934 | 71,248 |

## 3. 쿼리별 — 정상 모드 (마지막 반복 기준)

| id | Before 조사 대상 → runbook | After 조사 대상 → runbook | Before p50(s) | After p50(s) |
|---|---|---|---|---|
| r1 | payments-service → cpu-spike ✅ | payments-service → cpu-spike ✅ | 5.5 | 5.78 |
| r2 | cache-service → memory-leak ✅ | cache-service → memory-leak ✅ | 4.75 | 6.41 |
| r3 | log-service → disk-full ✅ | log-service → disk-full ✅ | 5.04 | 5.35 |
| r4 | gateway-service, payments-service, auth-service → high-latency ❌ | gateway-service, payments-service → network-timeout ✅ | 5.64 | 6.68 |
| r5 | web-01, auth-service → high-latency ✅ | web-01, auth-service → cpu-spike ✅ | 4.98 | 6.17 |
| r6 | payments-service, cache-service → cpu-spike ✅ | payments-service, cache-service → memory-leak ✅ | 6.09 | 6.79 |
| r7 | auth-service → high-latency ✅ | auth-service → high-latency ✅ | 5.16 | 5.36 |
| r8 | auth-service → high-latency ❌ | - → - ✅ | 4.58 | 1.89 |
| r9 | - → - | - → - | 1.72 | 1.68 |
| r10 | - → - | - → - | 1.69 | 1.75 |
| s1 | auth-service → high-latency ❌ | - → - ✅ | 4.44 | 1.87 |
| s2 | auth-service → high-latency ❌ | - → - ✅ | 5.29 | 1.78 |
| s3 | auth-service, payments-service, cache-service → high-latency ✅ | auth-service, payments-service, cache-service → network-timeout ❌ | 6.4 | 6.78 |
| s4 | gateway-service, log-service → network-timeout ✅ | gateway-service, log-service → disk-full ✅ | 6.39 | 7.0 |
| s5 | cache-service → memory-leak ✅ | cache-service → memory-leak ✅ | 4.81 | 5.18 |
| s6 | auth-service → high-latency | gateway-service, auth-service, cache-service, log-service, payments-service, web-01 → network-timeout | 4.83 | 8.4 |
| b1 | web-01 → db-down ❌ | web-01 → cpu-spike ✅ | 4.78 | 4.36 |
| b2 | web-01 → db-down ❌ | web-01 → memory-leak ✅ | 5.89 | 5.95 |
| b3 | payments-service → cpu-spike ❌ | payments-service → db-down ✅ | 5.26 | 6.28 |
| b4 | gateway-service → network-timeout ✅ | gateway-service → network-timeout ✅ | 5.51 | 5.6 |
| b5 | auth-service → high-latency ❌ | auth-service → disk-full ✅ | 5.16 | 5.78 |
