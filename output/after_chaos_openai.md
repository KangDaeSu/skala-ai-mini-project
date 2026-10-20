# 평가 결과 — after / chaos / openai

- 실행 시각: 2026-10-20T15:38:58  · 커밋: `f585c7b`  · 반복: 2회
- 모델: fast=`openai:gpt-4o-mini`, quality=`openai:gpt-4o` · runbook 선택: `rag(openai:text-embedding-3-small)`
- 장애 주입: `hang=0.15,error=0.10,badjson=0.10` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|
| 53 | 23 | 32/32 (100%) | 23/23 (100%) | 11 | 21/32 (66%) | 24.41 | 98.89 | 3.09 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|---|
| regression | 22 | 10 | 14/14 (100%) | 10/10 (100%) | 4 | 10/14 (71%) | 29.86 | 98.89 | 3.5 |
| unknown-system | 6 | 3 | 6/6 (100%) | 3/3 (100%) | 1 | 5/6 (83%) | 2.35 | 32.49 | 2 |
| chat | 7 | 3 | 4/4 (100%) | 3/3 (100%) | 3 | 1/4 (25%) | 16.43 | 31.4 | 2 |
| multi-system | 11 | 4 | 4/4 (100%) | 4/4 (100%) | 2 | 2/4 (50%) | 62.28 | 67.93 | 4 |
| single-system | 4 | 2 | 2/2 (100%) | 2/2 (100%) | 1 | 1/2 (50%) | 45.66 | 65.88 | 3 |
| no-system | 3 | 1 | 2/2 (100%) | 1/1 (100%) | 0 | 2/2 (100%) | 9.86 | 10.25 | 4 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | payments-service | cpu-spike | 5.45 | 6.23 | error, badjson |
| r2 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | cache-service | memory-leak | 32.18 | 58.41 | hang, hang |
| r3 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | log-service | disk-full | 53.59 | 65.16 | badjson, hang, hang, error, hang |
| r4 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | gateway-service, payments-service | network-timeout | 53.11 | 82.86 | error, badjson, hang, hang, hang, error |
| r5 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | web-01, auth-service | cpu-spike | 21.72 | 36.34 | hang |
| r6 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | payments-service, cache-service | memory-leak | 53.63 | 98.89 | hang, hang |
| r7 | 2/2 (100%) | 2/2 (100%) | 1/2 (50%) | 1/2 (50%) | - | - | 25.42 | 45.56 | error, badjson, hang, hang |
| r8 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | - | - | - | 1.92 | 1.99 | - |
| r9 | 2/2 (100%) | 2/2 (100%) | - | - | - | - | 1.5 | 1.6 | error, badjson |
| r10 | 2/2 (100%) | 2/2 (100%) | - | - | - | - | 31.34 | 31.4 | hang, hang, error, badjson, hang |
| s1 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | - | - | - | 27.67 | 32.49 | hang, hang, error, error, error |
| s2 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | - | - | - | 2.3 | 2.7 | error |
| s3 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 0/2 (0%) | auth-service, payments-service, cache-service | network-timeout | 52.31 | 65.8 | error, error, hang, badjson, hang, error |
| s4 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | gateway-service, log-service | disk-full | 63.34 | 67.93 | error, hang, hang, error, hang |
| s5 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | cache-service | memory-leak | 45.66 | 65.88 | hang, hang, badjson, error |
| s6 | 2/2 (100%) | 2/2 (100%) | - | - | gateway-service, auth-service, cache-service, log-service, payments-service, web-01 | network-timeout | 9.86 | 10.25 | error, error, error |
