# 평가 결과 — step3 / chaos / ollama

- 실행 시각: 2026-10-20T14:53:11  · 커밋: `12a7cc7`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b`
- 장애 주입: `hang=0.15,error=0.10,badjson=0.10` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|
| 18 | 10 | 16/16 (100%) | 10/10 (100%) | 4 | 12/16 (75%) | 16.89 | 92.68 | 3.12 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|---|
| regression | 8 | 5 | 7/7 (100%) | 5/5 (100%) | 2 | 5/7 (71%) | 14.57 | 70.97 | 3.43 |
| unknown-system | 1 | 1 | 3/3 (100%) | 1/1 (100%) | 0 | 3/3 (100%) | 1.03 | 31.33 | 2 |
| chat | 5 | 2 | 2/2 (100%) | 2/2 (100%) | 2 | 0/2 (0%) | 15.7 | 30.74 | 2 |
| multi-system | 3 | 1 | 2/2 (100%) | 1/1 (100%) | 0 | 2/2 (100%) | 55.95 | 92.68 | 4 |
| single-system | 1 | 1 | 1/1 (100%) | 1/1 (100%) | 0 | 1/1 (100%) | 75.47 | 75.47 | 4 |
| no-system | 0 | 0 | 1/1 (100%) | - | 0 | 1/1 (100%) | 14.1 | 14.1 | 4 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | cpu-spike | 14.57 | 14.57 | error |
| r2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 66.26 | 66.26 | hang, hang |
| r3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | log-service | disk-full | 10.76 | 10.76 | badjson |
| r4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | gateway-service, payments-service | cpu-spike | 70.97 | 70.97 | error, badjson, hang |
| r5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | web-01, auth-service | high-latency | 14.36 | 14.36 | - |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | cpu-spike | 42.39 | 42.39 | hang |
| r7 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 0/1 (0%) | - | - | 1.47 | 1.47 | - |
| r8 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 1.03 | 1.03 | - |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.65 | 0.65 | error, badjson |
| r10 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 30.74 | 30.74 | hang, hang, error |
| s1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 31.33 | 31.33 | hang |
| s2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 0.89 | 0.89 | - |
| s3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | auth-service, payments-service, cache-service | high-latency | 19.22 | 19.22 | - |
| s4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | gateway-service, log-service | network-timeout | 92.68 | 92.68 | error, hang, hang |
| s5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 75.47 | 75.47 | hang |
| s6 | 1/1 (100%) | 1/1 (100%) | - | - | auth-service | high-latency | 14.1 | 14.1 | - |
