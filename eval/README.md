# 평가 도구 (eval/)

Before/After를 **같은 데이터셋·같은 조건**으로 측정하기 위한 도구다. `agent/` 코드는 한 줄도
바꾸지 않고, 그래프를 프로세스 안에서 직접 실행하면서 바깥에서 관찰·장애 주입만 한다.

| 파일 | 역할 |
|---|---|
| `dataset.json` | 쿼리 16건과 정답 라벨 (route, 조사 대상, 허용 runbook) |
| `run_eval.py` | deps 생성 → 그래프 실행 → 채점 → `output/`에 JSON·마크다운 저장 |
| `chaos.py` | 장애 주입기 — httpx 전송 계층을 바꿔치기해 LLM API 호출에 장애를 낸다 |

## 실행

```bash
# 정상 모드 (품질)
.venv/bin/python3 eval/run_eval.py --label before --backend openai --repeat 3
# 장애 주입 모드 (신뢰성)
.venv/bin/python3 eval/run_eval.py --label before --backend openai --mode chaos --repeat 2
```

옵션: `--only r1 r8` (일부만 실행), `--chaos-rates hang=0.15,error=0.10,badjson=0.10`,
`--chaos-seed 42`, `--out <폴더>`

결과: `output/{label}_{mode}_{backend}.json`(요약 + 실행별 원본), `.md`(보고서용 표)

## 두 모드의 차이

둘 다 같은 데이터셋을 같은 코드로 OpenAI에서 실행한다. 다른 점은 OpenAI API가 정상인지,
일부러 고장 낸 상태인지뿐이다.

| 구분 | 정상 모드 | 장애 주입 모드 |
|---|---|---|
| OpenAI 호출 | 그대로 OpenAI로 감 | 일부 호출을 가로채 가짜 실패 응답으로 바꿈 |
| 확인하려는 것 | **품질** — 제대로 진단하나 | **신뢰성** — 외부 API가 고장 나도 버티나 |
| 주요 지표 | route·대상·runbook 정확도, 지연, 토큰 | 성공률, 장애 시 성공률, 최대 지연 |

정상 모드만으로는 신뢰성 개선을 증명할 수 없다 — OpenAI는 평소 안정적이라 Before도 100%
성공한다. 장애 주입 모드는 타임아웃·재시도·폴백의 효과를 보여주는 유일한 방법이고, 정상
모드는 개선 과정에서 품질이 나빠지지 않았는지 보는 회귀 검사 역할을 한다.

## 장애 주입의 동작

### 어디서 가로채나

```
graph.py   route_node()
  → openai_llm.py   OpenAIFastLLM.route()
    → openai_llm.py   OpenAILLM._chat()
      → httpx.post("https://api.openai.com/v1/chat/completions", timeout=120)
        → httpx.Client.send()
          → httpx.HTTPTransport.handle_request()   ◀ 여기를 바꿔치기
            → (실제 네트워크 전송)
```

`chaos.py`는 실제로 네트워크에 요청을 보내는 `handle_request`(비동기는
`handle_async_request`)를 자기 함수로 바꿔 끼운다. 에이전트 코드는 그대로이고, 에이전트 입장에서는
진짜 OpenAI가 고장 난 것과 구별할 수 없다. 장애가 걸린 호출은 OpenAI로 실제 요청이 나가지 않는다.

### 장애를 걸지 말지 정하는 방법

1. `seed | 쿼리 id | 반복 회차 | 이 쿼리의 몇 번째 호출인지`를 SHA-256으로 해시해 0~1 사이 값 `u`를 만든다.
2. `u < 0.15` → 응답 없음, `u < 0.25` → 503, `u < 0.35` → 깨진 JSON, 그 외 → 정상 통과.

난수가 아니라 해시라서, 같은 seed면 Before와 After에서 같은 쿼리의 같은 순번 호출이 같은
장애를 맞는다.

### 장애별로 일어나는 일

| 장애 | 가로챈 함수가 하는 일 | 에이전트 코드가 받는 것 |
|---|---|---|
| 응답 없음 (hang) | 요청의 read timeout(Before는 120초)만큼 실제로 기다린 뒤 `httpx.ReadTimeout` | OpenAI가 응답하지 않을 때와 똑같은 예외 |
| 503 (error) | OpenAI 형식의 503 응답을 그 자리에서 만들어 반환 | `raise_for_status()`에서 `HTTPStatusError` |
| 깨진 JSON (badjson) | 200 응답이지만 내용이 `{"route": "inci`처럼 잘림 (JSON 출력을 강제한 route·plan 요청에만) | `json.loads()` 실패 |

### MCP 장애 (`--chaos-mcp-rate`)

MCP는 HTTP가 아니라 stdio라서 전송 계층 대신 `MCPClient` 메서드(find_prompt·get_prompt·call_tool·
find_resource_template·read_resource)를 감싼다. 비율의 절반은 응답 없음(타임아웃이 끊어야 함),
절반은 연결 실패(ConnectionError). 기본값 0 — Before/After 비교 측정은 MCP 장애 없이 했다.

### 장애를 걸지 않는 범위

- MCP 호출 — `--chaos-mcp-rate`를 주지 않으면
- LangSmith 전송 — 대상 호스트를 OpenAI(`api.openai.com`)와 로컬 Ollama(`127.0.0.1`)로 한정
- 워밍업 요청, 다턴 시나리오의 앞선 턴(r10의 "제 이름은 민수입니다") — 측정하는 턴에만 건다

## 지표 정의

| 지표 | 정의 |
|---|---|
| success | 예외 없이 비어 있지 않은 답변이 나온 비율 |
| route_acc | chat / incident 분류가 기대값과 같은 비율 |
| target_acc | 조사한 모니터링 대상 집합 == 기대 집합 (모르는 시스템은 아무것도 조사하지 않아야 정답) |
| runbook_acc | 선택된 runbook이 모두 허용 목록 안에 있는 비율 (참고용) |
| latency | 쿼리 1건 전체 시간. 정상 모드는 성공한 실행만, `latency_max_all`은 실패 포함 |
| llm_calls / tokens | `_chat` 관찰 래퍼가 센 호출 수와 OpenAI `usage.total_tokens` |
| faulted_runs / success_when_faulted | 장애를 1번 이상 맞은 실행 수와 그중 성공 비율 |

## Before 결과 요약 (OpenAI, 커밋 `253fb4c`)

| 지표 | 정상 모드 (48회) | 장애 주입 모드 (32회) |
|---|---|---|
| 성공률 | 100% | 41% |
| 장애를 맞은 실행의 성공률 | — | 14% (3/22) |
| 최대 지연 | 7.6초 | 122.8초 |
| 대상 정확도 | 74% (모르는 시스템 0/9) | — |

- 응답 없음 11건은 전부 120초 대기 후 실패, 503 8건은 전부 즉시 실패
- 깨진 JSON 4건 중 3건은 기존 정규식 폴백으로 답변했지만, 2건은 "느려요" 같은 표현이 정규식에
  없어 장애 쿼리가 chat으로 잘못 분류됨
- 장애를 맞지 않은 10건은 전부 성공 — 실패 원인이 주입한 장애뿐이라는 뜻

## 한계

- 장애 비율이 호출 단위로 합계 35%라 쿼리의 약 70%가 장애를 1번 이상 맞는다 — 실제 운영보다
  훨씬 가혹한 스트레스 조건이다. After도 같은 비율·seed로 측정해야 비교가 공정하다.
- OpenAI도 temperature 0에서 결과가 조금씩 흔들려 반복 측정 평균을 쓴다.
- 모니터링 수치에 랜덤 jitter가 있어 정확한 수치 인용은 채점하지 않는다.
