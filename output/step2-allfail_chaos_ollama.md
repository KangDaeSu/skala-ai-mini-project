# 평가 결과 — step2-allfail / chaos / ollama

- 실행 시각: 2026-10-20T14:13:10  · 커밋: `c5d9f04`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b`
- 장애 주입: `error=1.0` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|
| 24 | 3 | 3/3 (100%) | 3/3 (100%) | 3 | 0/3 (0%) | 1.75 | 1.77 | 2.67 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|---|
| regression | 18 | 2 | 2/2 (100%) | 2/2 (100%) | 2 | 0/2 (0%) | 1.76 | 1.77 | 3 |
| chat | 6 | 1 | 1/1 (100%) | 1/1 (100%) | 1 | 0/1 (0%) | 0.67 | 0.67 | 2 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | cpu-spike | 1.77 | 1.77 | error, error, error, error, error, error, error, error, error |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | cpu-spike | 1.75 | 1.75 | error, error, error, error, error, error, error, error, error |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.67 | 0.67 | error, error, error, error, error, error |
