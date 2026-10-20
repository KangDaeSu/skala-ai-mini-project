# 5단계 — runbook 선택: 키워드 규칙 vs RAG (Ollama, 같은 21건)

- 키워드 규칙 정확도: **9/15 (60%)** · RAG(`nomic-embed-text`, 질의 0.8 + alert 0.2) 정확도: **12/15 (80%)**
- 성공률 21/21 (100%) → 21/21 (100%), 대상 정확도 17/18 (94%) → 17/18 (94%), p50 지연 13.36s → 12.95s

## 쿼리별

| id | 질의 | 정답 | 키워드 규칙 | RAG | RAG 유사도 (1·2위 차) |
|---|---|---|---|---|---|
| r1 | payments-service 결제 응답이 느려지고 CPU가 치솟았어요, 원인 확인해주세요 | cpu-spike | cpu-spike ✅ | cpu-spike ✅ | 0.6651 (0.0394) |
| r2 | cache-service 메모리 사용률이 계속 올라가고 있어요 | memory-leak | memory-leak ✅ | memory-leak ✅ | 0.6738 (0.054) |
| r3 | log-service 디스크 공간이 부족하다는 알림이 왔어요 | disk-full | disk-full ✅ | disk-full ✅ | 0.6848 (0.0219) |
| r4 | gateway-service에서 payments-service로 가는 요청이 타임아웃 나고 있어요 | network-timeout | cpu-spike ❌ | network-timeout ✅ | 0.6766 (0.0784) |
| r5 | web-01 CPU 급증, auth-service 커넥션 풀도 같이 확인해줘 | cpu-spike, high-latency | high-latency ✅ | high-latency ✅ | 0.6379 (0.0021) |
| r6 | payments-service랑 cache-service 둘 다 저하됐는데 공통 원인이 있는지 분석해줘 | cpu-spike, memory-leak | cpu-spike ✅ | memory-leak ✅ | 0.6425 (0.0107) |
| r7 | 로그인 응답이 느려요, 원인 확인해주세요 | high-latency | - ❌ | - ❌ | - |
| s3 | auth-service, payments-service, cache-service 전부 느려졌어요 | high-latency, cpu-spike, memory-leak | high-latency ✅ | high-latency ✅ | 0.6599 (0.0249) |
| s4 | gateway-service 타임아웃이랑 log-service 디스크 경고가 동시에 떴어요 | network-timeout, disk-full | network-timeout ✅ | network-timeout ✅ | 0.7048 (0.0687) |
| s5 | cache-service 힙 메모리가 한계에 가까워요 | memory-leak | memory-leak ✅ | memory-leak ✅ | 0.6673 (0.0435) |
| b1 | web-01 CPU 급증 원인 진단해줘 | cpu-spike | db-down ❌ | cpu-spike ✅ | 0.6118 (0.0049) |
| b2 | web-01 메모리 사용량이 계속 늘어나요, 누수 같아요 | memory-leak | db-down ❌ | network-timeout ❌ | 0.6349 (0.0146) |
| b3 | payments-service DB 연결이 끊기고 리플리케이션이 멈췄어요 | db-down | cpu-spike ❌ | db-down ✅ | 0.662 (0.0397) |
| b4 | gateway-service에서 504 타임아웃이 계속 나요 | network-timeout | network-timeout ✅ | network-timeout ✅ | 0.7062 (0.1363) |
| b5 | auth-service 디스크가 꽉 찼다는 알림이 왔어요 | disk-full | high-latency ❌ | high-latency ❌ | 0.6324 (0.0031) |
