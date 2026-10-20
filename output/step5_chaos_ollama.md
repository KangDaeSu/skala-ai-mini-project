# 평가 결과 — step5 / chaos / ollama

- 실행 시각: 2026-10-20T15:17:21  · 커밋: `4a2d422`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b` · runbook 선택: `rag(ollama:nomic-embed-text)`
- 장애 주입: `hang=0.15,error=0.10,badjson=0.10` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|
| 30 | 14 | 21/21 (100%) | 14/14 (100%) | 6 | 15/21 (71%) | 19.11 | 107.92 | 3.33 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|---|
| regression | 11 | 5 | 7/7 (100%) | 5/5 (100%) | 2 | 5/7 (71%) | 66.27 | 107.92 | 3.43 |
| unknown-system | 1 | 1 | 3/3 (100%) | 1/1 (100%) | 0 | 3/3 (100%) | 1.12 | 31.43 | 2 |
| chat | 5 | 2 | 2/2 (100%) | 2/2 (100%) | 2 | 0/2 (0%) | 15.71 | 30.75 | 2 |
| multi-system | 6 | 2 | 2/2 (100%) | 2/2 (100%) | 1 | 1/2 (50%) | 63.37 | 63.52 | 4 |
| single-system | 1 | 1 | 1/1 (100%) | 1/1 (100%) | 0 | 1/1 (100%) | 48.19 | 48.19 | 4 |
| no-system | 0 | 0 | 1/1 (100%) | - | 0 | 1/1 (100%) | 14.38 | 14.38 | 4 |
| runbook | 6 | 3 | 5/5 (100%) | 3/3 (100%) | 1 | 4/5 (80%) | 13.71 | 41.4 | 4 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | cpu-spike | 14.15 | 14.15 | error |
| r2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 66.27 | 66.27 | hang, hang |
| r3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | log-service | disk-full | 71.31 | 71.31 | badjson, hang |
| r4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | gateway-service, payments-service | network-timeout | 89.02 | 89.02 | error, badjson, hang, hang |
| r5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | web-01, auth-service | high-latency | 19.11 | 19.11 | - |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | memory-leak | 107.92 | 107.92 | hang, hang |
| r7 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 0/1 (0%) | - | - | 2.02 | 2.02 | - |
| r8 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 1.12 | 1.12 | - |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.67 | 0.67 | error, badjson |
| r10 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 30.75 | 30.75 | hang, hang, error |
| s1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 31.43 | 31.43 | hang |
| s2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 0.94 | 0.94 | - |
| s3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | auth-service, payments-service, cache-service | high-latency | 63.52 | 63.52 | error, error, hang |
| s4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | gateway-service, log-service | network-timeout | 63.21 | 63.21 | error, hang, hang |
| s5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 48.19 | 48.19 | hang |
| s6 | 1/1 (100%) | 1/1 (100%) | - | - | auth-service | network-timeout | 14.38 | 14.38 | - |
| b1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | web-01 | cpu-spike | 11.77 | 11.77 | - |
| b2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | web-01 | network-timeout | 41.4 | 41.4 | badjson, hang |
| b3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | db-down | 13.71 | 13.71 | error |
| b4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | gateway-service | network-timeout | 15.61 | 15.61 | - |
| b5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | auth-service | high-latency | 12.78 | 12.78 | error, error, error |
