# 평가 결과 — step7-mcp / chaos / ollama

- 실행 시각: 2026-10-20T19:11:17  · 커밋: `17c42d9`  · 반복: 1회
- 모델: fast=`ollama:qwen3:0.6b`, quality=`ollama:qwen3:8b` · runbook 선택: `rag(ollama:nomic-embed-text)`
- 장애 주입: `hang=0.15,error=0.10,badjson=0.10` · MCP `0.15` (seed=42)

## 전체

| faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|
| 54 | 17 | 21/21 (100%) | 17/17 (100%) | 12 | 9/21 (43%) | 30.64 | 60.04 | 3.24 |

## 카테고리별

| category | faults_injected | faulted_runs | success | success_when_faulted | degraded_runs | full_success | latency_p50 | latency_max_all | avg_llm_calls |
|---|---|---|---|---|---|---|---|---|---|
| regression | 21 | 6 | 7/7 (100%) | 6/6 (100%) | 5 | 2/7 (29%) | 60.02 | 60.04 | 3.43 |
| unknown-system | 1 | 1 | 3/3 (100%) | 1/1 (100%) | 0 | 3/3 (100%) | 0.75 | 31.3 | 2 |
| chat | 5 | 2 | 2/2 (100%) | 2/2 (100%) | 2 | 0/2 (0%) | 15.7 | 30.64 | 2 |
| multi-system | 11 | 2 | 2/2 (100%) | 2/2 (100%) | 2 | 0/2 (0%) | 60.03 | 60.03 | 4 |
| single-system | 1 | 1 | 1/1 (100%) | 1/1 (100%) | 0 | 1/1 (100%) | 41.03 | 41.03 | 4 |
| no-system | 0 | 0 | 1/1 (100%) | - | 0 | 1/1 (100%) | 8.92 | 8.92 | 4 |
| runbook | 15 | 5 | 5/5 (100%) | 5/5 (100%) | 3 | 2/5 (40%) | 25.86 | 51.19 | 3.6 |

## 쿼리별

| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |
|---|---|---|---|---|---|---|---|---|---|
| r1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | payments-service | - | 30.25 | 30.25 | error, mcp_error, mcp_error, mcp_hang, mcp_error, mcp_hang |
| r2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 60.04 | 60.04 | hang, hang |
| r3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | log-service | disk-full | 60.03 | 60.03 | mcp_error, badjson, mcp_error, hang |
| r4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | gateway-service, payments-service | network-timeout | 60.02 | 60.02 | error, badjson, mcp_error, hang, hang |
| r5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | web-01, auth-service | high-latency | 14.23 | 14.23 | mcp_error |
| r6 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service, cache-service | memory-leak | 60.03 | 60.03 | hang, mcp_hang, hang |
| r7 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 0/1 (0%) | - | - | 1.12 | 1.12 | - |
| r8 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 0.75 | 0.75 | - |
| r9 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 0.76 | 0.76 | error, badjson |
| r10 | 1/1 (100%) | 1/1 (100%) | - | - | - | - | 30.64 | 30.64 | hang, hang, error |
| s1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 31.3 | 31.3 | hang |
| s2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | - | - | - | 0.64 | 0.64 | - |
| s3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | auth-service, payments-service, cache-service | high-latency | 60.03 | 60.03 | mcp_hang, mcp_hang, error, error, hang |
| s4 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 1/1 (100%) | gateway-service | network-timeout | 60.03 | 60.03 | error, hang, mcp_error, mcp_hang, mcp_hang, hang |
| s5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | cache-service | memory-leak | 41.03 | 41.03 | hang |
| s6 | 1/1 (100%) | 1/1 (100%) | - | - | auth-service | network-timeout | 8.92 | 8.92 | - |
| b1 | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | 0/1 (0%) | - | - | 32.01 | 32.01 | mcp_hang, mcp_hang, mcp_hang |
| b2 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | web-01 | - | 51.19 | 51.19 | badjson, hang, mcp_error, mcp_hang, mcp_error |
| b3 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | payments-service | db-down | 20.6 | 20.6 | error, mcp_hang |
| b4 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | gateway-service | - | 25.86 | 25.86 | mcp_hang, mcp_hang |
| b5 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) | auth-service | high-latency | 11.39 | 11.39 | error, error, error |
