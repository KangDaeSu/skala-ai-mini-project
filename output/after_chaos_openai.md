# 평가 결과 — after / chaos / openai

- 실행 시각: 2026-10-21T12:02:33  · 커밋: `d3c9cc5`  · 반복: 2회
- 모델: fast=`openai:gpt-4o-mini`, quality=`openai:gpt-4o` · runbook 선택: `rag(openai:text-embedding-3-small)`
- 장애 주입: `hang=0.15,error=0.10,badjson=0.10` · MCP `0.0` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|
| 50 | 22 | 32/32 (100%) | 22/22 (100%) | 10 | 22/32 (69%) | 14.47 | 45.48 | 2.78 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|---|
| regression | 22 | 10 | 14/14 (100%) | 10/10 (100%) | 4 | 10/14 (71%) | 18.34 | 45.48 | 3.07 |
| unknown-system | 6 | 3 | 6/6 (100%) | 3/3 (100%) | 1 | 5/6 (83%) | 2.62 | 17.39 | 2 |
| chat | 7 | 3 | 4/4 (100%) | 3/3 (100%) | 3 | 1/4 (25%) | 8.98 | 22.6 | 2 |
| multi-system | 8 | 3 | 4/4 (100%) | 3/3 (100%) | 1 | 3/4 (75%) | 34.9 | 38.2 | 3.5 |
| single-system | 4 | 2 | 2/2 (100%) | 2/2 (100%) | 1 | 1/2 (50%) | 25.9 | 35.45 | 3 |
| no-system | 3 | 1 | 2/2 (100%) | 1/1 (100%) | 0 | 2/2 (100%) | 6.7 | 8.1 | 3 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | payments-service | cpu-spike | 4.4 | 5.3 | error, badjson |
| r2 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | cache-service | memory-leak | 18.0 | 30.83 | hang, hang |
| r3 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | log-service | disk-full | 30.52 | 34.09 | badjson, hang, hang, error, hang |
| r4 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | gateway-service, payments-service | network-timeout | 30.75 | 45.48 | error, badjson, hang, hang, hang |
| r5 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | web-01, auth-service | cpu-spike | 12.91 | 20.65 | hang |
| r6 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | payments-service, cache-service | memory-leak | 22.43 | 38.32 | hang, hang |
| r7 | 2/2 (100%) | 2/2 (100%) | 1/2 (50%) | 1/2 (50%) | - | - | 18.52 | 32.11 | error, badjson, hang, hang, error |
| r8 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | - | - | - | 2.08 | 2.3 | - |
| r9 | 2/2 (100%) | 2/2 (100%) | - | - | - | - | 1.46 | 1.62 | error, badjson |
| r10 | 2/2 (100%) | 2/2 (100%) | - | - | - | - | 19.47 | 22.6 | hang, hang, error, badjson, hang |
| s1 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | - | - | - | 15.16 | 17.39 | hang, hang, error, error, error |
| s2 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | - | - | - | 2.49 | 2.93 | error |
| s3 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 0/2 (0%) | auth-service, payments-service, cache-service | network-timeout | 21.89 | 36.62 | badjson, hang, error |
| s4 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | gateway-service, log-service | disk-full | 35.69 | 38.2 | error, hang, hang, error, hang |
| s5 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | cache-service | memory-leak | 25.9 | 35.45 | hang, hang, badjson, error |
| s6 | 2/2 (100%) | 2/2 (100%) | - | - | gateway-service, auth-service, cache-service, log-service, payments-service, web-01 | network-timeout | 6.7 | 8.1 | error, error, error |
