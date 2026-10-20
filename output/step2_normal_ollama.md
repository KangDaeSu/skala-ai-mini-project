# 평가 결과 — step2 / normal / ollama

- 실행 시각: 2026-10-20T14:25:26  · 커밋: `c5d9f04`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b`

## 전체

| success | route_acc | target_acc | runbook_acc | latency_p50 | latency_p95 | latency_max | avg_llm_calls | avg_tokens |
|---|---|---|---|---|---|---|---|---|
| 16/16 (100%) | 16/16 (100%) | 6/13 (46%) | 9/10 (90%) | 14.57 | 16.8 | 16.9 | 3.75 | 1182.6 |

## 카테고리별

| category | success | route_acc | target_acc | runbook_acc | latency_p50 | latency_p95 | latency_max | avg_llm_calls | avg_tokens |
|---|---|---|---|---|---|---|---|---|---|
| regression | 7/7 (100%) | 7/7 (100%) | 5/7 (71%) | 6/7 (86%) | 13.72 | 16.54 | 16.63 | 4 | 1352 |
| unknown-system | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | - | 14.19 | 16.63 | 16.9 | 4 | 1253.3 |
| chat | 2/2 (100%) | 2/2 (100%) | - | - | 0.32 | 0.35 | 0.35 | 2 | 333.5 |
| multi-system | 2/2 (100%) | 2/2 (100%) | 0/2 (0%) | 2/2 (100%) | 15.87 | 16.68 | 16.77 | 4 | 1266.5 |
| single-system | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 16.42 | 16.42 | 16.42 | 4 | 1243 |
| no-system | 1/1 (100%) | 1/1 (100%) | - | - | 15.87 | 15.87 | 15.87 | 4 | 1255 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | cpu-spike | 16.63 | 16.63 | - |
| r2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 13.0 | 13.0 | - |
| r3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | log-service | disk-full | 12.73 | 12.73 | - |
| r4 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 0/1 (0%) | auth-service, cache-service, gateway-service, log-service, payments-service | high-latency | 13.72 | 13.72 | - |
| r5 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | auth-service, cache-service, gateway-service, log-service | high-latency | 12.53 | 12.53 | - |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | cpu-spike | 16.22 | 16.22 | - |
| r7 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | auth-service | high-latency | 16.33 | 16.33 | - |
| r8 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 14.19 | 14.19 | - |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.35 | 0.35 | - |
| r10 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.3 | 0.3 | - |
| s1 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 14.19 | 14.19 | - |
| s2 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 16.9 | 16.9 | - |
| s3 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | auth-service | high-latency | 16.77 | 16.77 | - |
| s4 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | gateway-service | network-timeout | 14.96 | 14.96 | - |
| s5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 16.42 | 16.42 | - |
| s6 | 1/1 (100%) | 1/1 (100%) | - | - | auth-service | high-latency | 15.87 | 15.87 | - |
