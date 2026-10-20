# 평가 결과 — before-runbook / normal / openai

- 실행 시각: 2026-10-20T15:31:12  · 커밋: `6b73c78`  · 반복: 3회
- 모델: fast=`openai:gpt-4o-mini`, quality=`openai:gpt-4o` · runbook 선택: `keyword`

## 전체

| success | route_acc | target_acc | runbook_acc | latency_p50 | latency_p95 | latency_max | avg_llm_calls | avg_tokens |
|---|---|---|---|---|---|---|---|---|
| 15/15 (100%) | 15/15 (100%) | 15/15 (100%) | 3/15 (20%) | 5.16 | 6.91 | 7.05 | 3.2 | 1014.1 |

## 카테고리별

| category | success | route_acc | target_acc | runbook_acc | latency_p50 | latency_p95 | latency_max | avg_llm_calls | avg_tokens |
|---|---|---|---|---|---|---|---|---|---|
| runbook | 15/15 (100%) | 15/15 (100%) | 15/15 (100%) | 3/15 (20%) | 5.16 | 6.91 | 7.05 | 3.2 | 1014.1 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| b1 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | web-01 | db-down | 4.78 | 4.84 | - |
| b2 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | web-01 | db-down | 5.89 | 6.85 | - |
| b3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | payments-service | cpu-spike | 5.26 | 7.05 | - |
| b4 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | gateway-service | network-timeout | 5.51 | 6.02 | - |
| b5 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0/3 (0%) | auth-service | high-latency | 5.16 | 5.53 | - |
