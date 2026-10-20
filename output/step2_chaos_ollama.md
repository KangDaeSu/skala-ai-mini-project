# 평가 결과 — step2 / chaos / ollama

- 실행 시각: 2026-10-20T14:13:47  · 커밋: `c5d9f04`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b`
- 장애 주입: `hang=0.15,error=0.10,badjson=0.10` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|
| 21 | 11 | 16/16 (100%) | 11/11 (100%) | 5 | 11/16 (69%) | 24.09 | 96.1 | 3.62 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|---|
| regression | 8 | 5 | 7/7 (100%) | 5/5 (100%) | 2 | 5/7 (71%) | 17.46 | 72.73 | 3.71 |
| unknown-system | 4 | 2 | 3/3 (100%) | 2/2 (100%) | 1 | 2/3 (67%) | 77.63 | 90.62 | 4 |
| chat | 5 | 2 | 2/2 (100%) | 2/2 (100%) | 2 | 0/2 (0%) | 15.74 | 30.73 | 2 |
| multi-system | 3 | 1 | 2/2 (100%) | 1/1 (100%) | 0 | 2/2 (100%) | 56.13 | 96.1 | 4 |
| single-system | 1 | 1 | 1/1 (100%) | 1/1 (100%) | 0 | 1/1 (100%) | 73.89 | 73.89 | 4 |
| no-system | 0 | 0 | 1/1 (100%) | - | 0 | 1/1 (100%) | 15.21 | 15.21 | 4 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | cpu-spike | 16.24 | 16.24 | error |
| r2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 66.32 | 66.32 | hang, hang |
| r3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | log-service | disk-full | 13.1 | 13.1 | badjson |
| r4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | gateway-service, payments-service | cpu-spike | 72.73 | 72.73 | error, badjson, hang |
| r5 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | auth-service, cache-service, gateway-service, log-service | high-latency | 12.24 | 12.24 | - |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | cpu-spike | 46.91 | 46.91 | hang |
| r7 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | auth-service | high-latency | 17.46 | 17.46 | - |
| r8 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 15.07 | 15.07 | - |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.75 | 0.75 | error, badjson |
| r10 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 30.73 | 30.73 | hang, hang, error |
| s1 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 90.62 | 90.62 | hang, hang, hang |
| s2 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | - | auth-service | high-latency | 77.63 | 77.63 | hang |
| s3 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | auth-service | high-latency | 16.17 | 16.17 | - |
| s4 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | gateway-service | network-timeout | 96.1 | 96.1 | error, hang, hang |
| s5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 73.89 | 73.89 | hang |
| s6 | 1/1 (100%) | 1/1 (100%) | - | - | auth-service | high-latency | 15.21 | 15.21 | - |
