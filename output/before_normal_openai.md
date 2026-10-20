# 평가 결과 — before / normal / openai

- 실행 시각: 2026-10-20T11:43:03  · 커밋: `253fb4c`  · 반복: 3회
- 모델: fast=`openai:gpt-4o-mini`, quality=`openai:gpt-4o`

## 전체

| success | route_acc | target_acc | runbook_acc | latency_p50 | latency_p95 | latency_max | avg_llm_calls | avg_tokens |
|---|---|---|---|---|---|---|---|---|
| 48/48 (100%) | 48/48 (100%) | 29/39 (74%) | 27/30 (90%) | 4.96 | 6.66 | 7.57 | 3.1 | 1035.9 |

## 카테고리별

| category | success | route_acc | target_acc | runbook_acc | latency_p50 | latency_p95 | latency_max | avg_llm_calls | avg_tokens |
|---|---|---|---|---|---|---|---|---|---|
| regression | 21/21 (100%) | 21/21 (100%) | 20/21 (95%) | 18/21 (86%) | 5.37 | 6.14 | 6.69 | 3.29 | 1141.5 |
| unknown-system | 9/9 (100%) | 9/9 (100%) | 0/9 (0%) | - | 4.75 | 6.08 | 6.61 | 3 | 1059.7 |
| chat | 6/6 (100%) | 6/6 (100%) | - | - | 1.71 | 2.29 | 2.47 | 2 | 241 |
| multi-system | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) | 6.39 | 7.45 | 7.57 | 3.83 | 1400.7 |
| single-system | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 4.81 | 4.84 | 4.84 | 3 | 1039 |
| no-system | 3/3 (100%) | 3/3 (100%) | - | - | 4.83 | 4.91 | 4.92 | 3 | 1082.3 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) |
|---|---|---|---|---|---|---|---|
| r1 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | payments-service | cpu-spike | 5.5 |
| r2 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | cache-service | memory-leak | 4.75 |
| r3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | log-service | disk-full | 5.04 |
| r4 | 3/3 (100%) | 3/3 (100%) | 2/3 (67%) | 0/3 (0%) | gateway-service, payments-service, auth-service | high-latency | 5.64 |
| r5 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | web-01, auth-service | high-latency | 4.98 |
| r6 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | payments-service, cache-service | cpu-spike | 6.09 |
| r7 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | auth-service | high-latency | 5.16 |
| r8 | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | - | auth-service | high-latency | 4.58 |
| r9 | 3/3 (100%) | 3/3 (100%) | - | - | - | - | 1.72 |
| r10 | 3/3 (100%) | 3/3 (100%) | - | - | - | - | 1.69 |
| s1 | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | - | auth-service | high-latency | 4.44 |
| s2 | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | - | auth-service | high-latency | 5.29 |
| s3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | auth-service, payments-service, cache-service | high-latency | 6.4 |
| s4 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | gateway-service, log-service | network-timeout | 6.39 |
| s5 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | cache-service | memory-leak | 4.81 |
| s6 | 3/3 (100%) | 3/3 (100%) | - | - | auth-service | high-latency | 4.83 |
