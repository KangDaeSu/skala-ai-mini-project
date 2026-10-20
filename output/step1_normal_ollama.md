# 평가 결과 — step1 / normal / ollama

- 실행 시각: 2026-10-20T13:36:42  · 커밋: `64a2895`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b`

## 전체

| success | route_acc | target_acc | runbook_acc | latency_p50 | latency_p95 | latency_max | avg_llm_calls | avg_tokens |
|---|---|---|---|---|---|---|---|---|
| 16/16 (100%) | 16/16 (100%) | 6/13 (46%) | 9/10 (90%) | 13.96 | 18.43 | 19.81 | 3.75 | 1184.3 |

## 카테고리별

| category | success | route_acc | target_acc | runbook_acc | latency_p50 | latency_p95 | latency_max | avg_llm_calls | avg_tokens |
|---|---|---|---|---|---|---|---|---|---|
| regression | 7/7 (100%) | 7/7 (100%) | 5/7 (71%) | 6/7 (86%) | 14.17 | 17.26 | 17.97 | 4 | 1349.3 |
| unknown-system | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | - | 13.85 | 19.21 | 19.81 | 4 | 1270.3 |
| chat | 2/2 (100%) | 2/2 (100%) | - | - | 0.33 | 0.37 | 0.37 | 2 | 329.5 |
| multi-system | 2/2 (100%) | 2/2 (100%) | 0/2 (0%) | 2/2 (100%) | 14.13 | 15.1 | 15.21 | 4 | 1266.5 |
| single-system | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 14.7 | 14.7 | 14.7 | 4 | 1246 |
| no-system | 1/1 (100%) | 1/1 (100%) | - | - | 14.06 | 14.06 | 14.06 | 4 | 1255 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | cpu-spike | 17.97 | 17.97 | - |
| r2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 9.23 | 9.23 | - |
| r3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | log-service | disk-full | 11.13 | 11.13 | - |
| r4 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 0/1 (0%) | auth-service, cache-service, gateway-service, log-service, payments-service | high-latency | 14.17 | 14.17 | - |
| r5 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | auth-service, cache-service, gateway-service, log-service | high-latency | 12.58 | 12.58 | - |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | cpu-spike | 14.64 | 14.64 | - |
| r7 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | auth-service | high-latency | 15.61 | 15.61 | - |
| r8 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 13.85 | 13.85 | - |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.37 | 0.37 | - |
| r10 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.3 | 0.3 | - |
| s1 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 13.79 | 13.79 | - |
| s2 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 19.81 | 19.81 | - |
| s3 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | auth-service | high-latency | 15.21 | 15.21 | - |
| s4 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | gateway-service | network-timeout | 13.05 | 13.05 | - |
| s5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 14.7 | 14.7 | - |
| s6 | 1/1 (100%) | 1/1 (100%) | - | - | auth-service | high-latency | 14.06 | 14.06 | - |
