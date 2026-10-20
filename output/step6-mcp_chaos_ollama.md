# 평가 결과 — step6-mcp / chaos / ollama

- 실행 시각: 2026-10-20T18:22:13  · 커밋: `f066b5f`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b` · runbook 선택: `rag(ollama:nomic-embed-text)`
- 장애 주입: `hang=0.15,error=0.10,badjson=0.10` · MCP `0.15` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|
| 54 | 17 | 21/21 (100%) | 17/17 (100%) | 10 | 11/21 (52%) | 31.28 | 115.25 | 3.24 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|---|
| regression | 21 | 6 | 7/7 (100%) | 6/6 (100%) | 3 | 4/7 (57%) | 60.69 | 115.25 | 3.43 |
| unknown-system | 1 | 1 | 3/3 (100%) | 1/1 (100%) | 0 | 3/3 (100%) | 1.2 | 31.28 | 2 |
| chat | 5 | 2 | 2/2 (100%) | 2/2 (100%) | 2 | 0/2 (0%) | 15.67 | 30.6 | 2 |
| multi-system | 11 | 2 | 2/2 (100%) | 2/2 (100%) | 2 | 0/2 (0%) | 83.14 | 84.72 | 4 |
| single-system | 1 | 1 | 1/1 (100%) | 1/1 (100%) | 0 | 1/1 (100%) | 42.96 | 42.96 | 4 |
| no-system | 0 | 0 | 1/1 (100%) | - | 0 | 1/1 (100%) | 10.89 | 10.89 | 4 |
| runbook | 15 | 5 | 5/5 (100%) | 5/5 (100%) | 3 | 2/5 (40%) | 28.65 | 53.36 | 3.6 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | payments-service | - | 31.61 | 31.61 | error, mcp_error, mcp_error, mcp_hang, mcp_error, mcp_hang |
| r2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 60.69 | 60.69 | hang, hang |
| r3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | log-service | disk-full | 72.41 | 72.41 | mcp_error, badjson, mcp_error, hang |
| r4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | gateway-service, payments-service | network-timeout | 86.26 | 86.26 | error, badjson, mcp_error, hang, hang |
| r5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | web-01, auth-service | high-latency | 14.42 | 14.42 | mcp_error |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | memory-leak | 115.25 | 115.25 | hang, mcp_hang, hang |
| r7 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 0/1 (0%) | - | - | 1.79 | 1.79 | - |
| r8 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 1.2 | 1.2 | - |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.73 | 0.73 | error, badjson |
| r10 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 30.6 | 30.6 | hang, hang, error |
| s1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 31.28 | 31.28 | hang |
| s2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 0.86 | 0.86 | - |
| s3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | auth-service, payments-service, cache-service | high-latency | 84.72 | 84.72 | mcp_hang, mcp_hang, error, error, hang |
| s4 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | gateway-service | network-timeout | 81.57 | 81.57 | error, hang, mcp_error, mcp_hang, mcp_hang, hang |
| s5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 42.96 | 42.96 | hang |
| s6 | 1/1 (100%) | 1/1 (100%) | - | - | auth-service | network-timeout | 10.89 | 10.89 | - |
| b1 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 0/1 (0%) | - | - | 32.16 | 32.16 | mcp_hang, mcp_hang, mcp_hang |
| b2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | web-01 | - | 53.36 | 53.36 | badjson, hang, mcp_error, mcp_hang, mcp_error |
| b3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | db-down | 27.5 | 27.5 | error, mcp_hang |
| b4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | gateway-service | - | 28.65 | 28.65 | mcp_hang, mcp_hang |
| b5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | auth-service | high-latency | 20.42 | 20.42 | error, error, error |
