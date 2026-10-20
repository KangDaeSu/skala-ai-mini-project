# 평가 결과 — step1 / chaos / ollama

- 실행 시각: 2026-10-20T13:48:34  · 커밋: `64a2895`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b`
- 장애 주입: `hang=0.15,error=0.10,badjson=0.10` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|
| 20 | 11 | 14/16 (88%) | 9/11 (82%) | 15.52 | 93.46 | 3.5 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|
| regression | 8 | 5 | 7/7 (100%) | 5/5 (100%) | 16.81 | 75.65 | 3.71 |
| unknown-system | 4 | 2 | 2/3 (67%) | 1/2 (50%) | 43.77 | 77.17 | 3.67 |
| chat | 4 | 2 | 1/2 (50%) | 1/2 (50%) | 0.75 | 30.04 | 1.5 |
| multi-system | 3 | 1 | 2/2 (100%) | 1/1 (100%) | 53.59 | 93.46 | 4 |
| single-system | 1 | 1 | 1/1 (100%) | 1/1 (100%) | 71.19 | 71.19 | 4 |
| no-system | 0 | 0 | 1/1 (100%) | - | 12.82 | 12.82 | 4 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | cpu-spike | 16.81 | 16.81 | error |
| r2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 63.67 | 63.67 | hang, hang |
| r3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | log-service | disk-full | 11.09 | 11.09 | badjson |
| r4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | gateway-service, payments-service | cpu-spike | 75.65 | 75.65 | error, badjson, hang |
| r5 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | auth-service, cache-service, gateway-service, log-service | high-latency | 10.67 | 10.67 | - |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | cpu-spike | 41.73 | 41.73 | hang |
| r7 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | auth-service | high-latency | 14.23 | 14.23 | - |
| r8 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 12.36 | 12.36 | - |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.75 | 0.75 | error, badjson |
| r10 | 0/1 (0%) | - | - | - | - | - | None | 30.04 | hang, hang |
| s1 | 0/1 (0%) | - | - | - | - | - | None | 77.17 | hang, hang, hang |
| s2 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 75.18 | 75.18 | hang |
| s3 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | auth-service | high-latency | 13.72 | 13.72 | - |
| s4 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | gateway-service | network-timeout | 93.46 | 93.46 | error, hang, hang |
| s5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 71.19 | 71.19 | hang |
| s6 | 1/1 (100%) | 1/1 (100%) | - | - | auth-service | high-latency | 12.82 | 12.82 | - |
