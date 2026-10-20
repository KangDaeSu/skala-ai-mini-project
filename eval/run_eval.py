"""Before/After 공통 평가 스크립트 — 정상 모드 / 장애 주입 모드.

server.py의 lifespan과 같은 방식으로 SupervisorDeps를 만들고 그래프를 프로세스 안에서
직접 실행한다. 서버를 띄우지 않아도 되고, Before/After 어느 코드에도 그대로 적용된다
(agent/ 코드는 한 줄도 바꾸지 않는다 — LLM 호출 횟수·토큰은 _chat을 감싸서 관찰만 한다).
장애 주입 모드는 eval/chaos.py가 httpx 전송 계층에서 LLM API 호출에 장애를 낸다.

실행 (프로젝트 루트에서):
    .venv/bin/python3 eval/run_eval.py --label before --backend openai --repeat 3
    .venv/bin/python3 eval/run_eval.py --label before --backend openai --mode chaos --repeat 1
결과:
    output/{label}_{mode}_{backend}.json   (요약 + 실행별 원본 기록)
    output/{label}_{mode}_{backend}.md     (보고서에 붙여 넣을 요약표)
"""
import argparse
import asyncio
import inspect
import json
import os
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import chaos

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from langsmith import traceable

CALLS: list[dict] = []   # 현재 쿼리 1건 동안의 LLM 호출 기록 (쿼리마다 비운다)


def _observe(cls, method_name: str) -> None:
    """LLM 어댑터의 저수준 호출(_chat/_chat_stream)을 감싸 호출 수·토큰·소요시간만 기록한다."""
    orig = getattr(cls, method_name)

    def record(self, started, usage, ok, error=None):
        CALLS.append({"model": self.name, "ok": ok, "error": error,
                      "tokens": (usage or {}).get("tokens", 0),
                      "sec": round(time.perf_counter() - started, 2)})

    if inspect.iscoroutinefunction(orig):
        async def wrapped(self, *args, **kwargs):
            started = time.perf_counter()
            try:
                content, usage = await orig(self, *args, **kwargs)
            except Exception as e:
                record(self, started, None, False, type(e).__name__)
                raise
            record(self, started, usage, True)
            return content, usage
    else:
        def wrapped(self, *args, **kwargs):
            started = time.perf_counter()
            try:
                content, usage = orig(self, *args, **kwargs)
            except Exception as e:
                record(self, started, None, False, type(e).__name__)
                raise
            record(self, started, usage, True)
            return content, usage
    setattr(cls, method_name, wrapped)


def _install_observers(backend: str) -> None:
    if backend == "openai":
        from agent.openai_llm import OpenAILLM
        _observe(OpenAILLM, "_chat")
    elif backend == "ollama":
        from agent.ollama_llm import OllamaLLM
        _observe(OllamaLLM, "_chat")
        _observe(OllamaLLM, "_chat_stream")


def _git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


try:   # After 코드에만 있다 — Before 코드(fallback.py 없음)에서도 평가가 돌아가게 한다
    from agent.fallback import tag_request_run
except ImportError:
    def tag_request_run(result: dict) -> None:
        pass


@traceable(name="chat_request")
async def _run_turn(graph, store, query: str, thread_id: str) -> dict:
    """server.py의 _handle_chat과 같은 순서: 이력 로드 → 그래프 실행 → 이력 저장.
    루트 run 이름도 chat_request로 맞춰 LangSmith에서 서버 요청과 같은 모양으로 보인다."""
    history = store.load(thread_id)
    result = await graph.ainvoke({"query": query, "thread_id": thread_id, "history": history,
                                  "events": [], "cost_usd": 0.0})
    store.append(thread_id, "user", query)
    store.append(thread_id, "assistant", result["final"])
    tag_request_run(result)
    return result


def _score(item: dict, result: dict | None) -> dict:
    """한 번의 실행 결과를 기대값과 비교한다. 기대값이 None인 항목은 채점하지 않는다."""
    if result is None:
        return {}
    events = result.get("events", [])
    monitored = list(dict.fromkeys(e["target"] for e in events
                                   if e.get("type") == "TaskCompleted" and e.get("source") == "monitoring"))
    runbooks = list(dict.fromkeys(e["target"] for e in events
                                  if e.get("type") == "TaskCompleted" and e.get("source") == "runbook"))
    s = {"route": result.get("route"), "monitored": monitored, "runbooks": runbooks,
         "route_ok": result.get("route") == item["expect_route"]}
    if item.get("expect_targets") is not None:
        s["targets_ok"] = set(monitored) == set(item["expect_targets"])
    if item.get("expect_runbook") is not None:
        s["runbook_ok"] = bool(runbooks) and all(r in item["expect_runbook"] for r in runbooks)
    if item.get("expect_reply_contains"):
        s["reply_ok"] = all(w in result.get("final", "") for w in item["expect_reply_contains"])
    return s


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def _rate(runs: list[dict], key: str) -> str:
    vals = [r[key] for r in runs if key in r]
    return f"{sum(vals)}/{len(vals)} ({sum(vals) / len(vals):.0%})" if vals else "-"


def _summarize(runs: list[dict]) -> dict:
    lat = [r["elapsed_s"] for r in runs if r["success"]]
    faulted = [r for r in runs if r.get("faults")]
    return {
        "degraded_runs": sum(1 for r in runs if r.get("degraded", 0) > 0),
        "full_success": _rate([{"v": r["success"] and not r.get("degraded", 0)} for r in runs], "v"),
        "faults_injected": sum(len(r.get("faults", [])) for r in runs),
        "faulted_runs": len(faulted),
        "success_when_faulted": _rate(faulted, "success"),
        "latency_max_all": max(r["elapsed_s"] for r in runs) if runs else None,
        "runs": len(runs),
        "success": _rate(runs, "success"),
        "route_acc": _rate(runs, "route_ok"),
        "target_acc": _rate(runs, "targets_ok"),
        "runbook_acc": _rate(runs, "runbook_ok"),
        "reply_acc": _rate(runs, "reply_ok"),
        "latency_p50": _pct(lat, 0.5), "latency_p95": _pct(lat, 0.95),
        "latency_max": max(lat) if lat else None,
        "avg_llm_calls": round(statistics.mean(r["llm_calls"] for r in runs), 2),
        "avg_tokens": round(statistics.mean(r["tokens"] for r in runs), 1),
        "total_tokens": sum(r["tokens"] for r in runs),
        "retries": sum(r.get("retry_count", 0) for r in runs),
        "avg_validation_attempts": round(statistics.mean(r.get("validation_attempts", 0) for r in runs), 2),
    }


def _markdown(meta: dict, overall: dict, by_cat: dict, per_item: dict) -> str:
    cols = ["success", "route_acc", "target_acc", "runbook_acc", "latency_p50", "latency_p95",
            "latency_max", "avg_llm_calls", "avg_tokens"]
    if meta["mode"] == "chaos":
        cols = ["faults_injected", "faulted_runs", "success", "success_when_faulted",
                "degraded_runs", "full_success", "latency_p50", "latency_max_all", "avg_llm_calls"]
    lines = [f"# 평가 결과 — {meta['label']} / {meta['mode']} / {meta['backend']}", "",
             f"- 실행 시각: {meta['started_at']}  · 커밋: `{meta['git_rev']}`  · 반복: {meta['repeat']}회",
             f"- 모델: fast=`{meta['fast_llm']}`, quality=`{meta['quality_llm']}`"
             f" · runbook 선택: `{meta.get('runbook_classifier', 'keyword')}`",
             *([f"- 장애 주입: `{meta['chaos_rates']}` (seed={meta['chaos_seed']})"]
               if meta["mode"] == "chaos" else []), "",
             "## 전체", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols),
             "| " + " | ".join(str(overall[c]) for c in cols) + " |", "",
             "## 카테고리별", "", "| category | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for cat, s in by_cat.items():
        lines.append(f"| {cat} | " + " | ".join(str(s[c]) for c in cols) + " |")
    lines += ["", "## 쿼리별", "", "| id | 성공 | route | 대상 | runbook | 조사한 대상 (마지막 실행) | runbook (마지막 실행) | p50(s) | 최대(s) | 주입 장애 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for qid, d in per_item.items():
        lines.append(f"| {qid} | {d['success']} | {d['route_acc']} | {d['target_acc']} | {d['runbook_acc']} "
                     f"| {', '.join(d['last_monitored']) or '-'} | {', '.join(d['last_runbooks']) or '-'} "
                     f"| {d['latency_p50']} | {d['latency_max_all']} | {', '.join(d['fault_names']) or '-'} |")
    return "\n".join(lines) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="before / after 등 결과 파일 이름표")
    ap.add_argument("--backend", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--only", nargs="*", help="이 id들만 실행 (스모크 테스트용)")
    ap.add_argument("--mode", default="normal", choices=["normal", "chaos"])
    ap.add_argument("--chaos-rates", default="hang=0.15,error=0.10,badjson=0.10")
    ap.add_argument("--chaos-seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "output"))
    args = ap.parse_args()

    os.environ["LLM_BACKEND"] = args.backend
    os.environ["SUPERVISOR_VERSION"] = "v2"
    os.environ["LANGCHAIN_PROJECT"] = f"skala-eval-{args.label}-{args.mode}-{args.backend}"

    from agent.deps import SupervisorDeps
    from agent.graph import build_graph
    from agent.mcp_client import MCPClient
    from agent.session_store import SqliteSessionStore
    from server import _build_llms

    _install_observers(args.backend)
    dataset = json.loads((ROOT / "eval" / "dataset.json").read_text())
    if args.only:
        dataset = [d for d in dataset if d["id"] in args.only]

    mcp = MCPClient()
    await mcp.start()
    backend, fast_llm, quality_llm = _build_llms()
    store = SqliteSessionStore(Path(":memory:"))   # 실제 session.db를 건드리지 않는다
    try:   # After 코드에만 있다 — Before 코드에서는 키워드 규칙으로 동작
        from agent.rag import build_retriever
        extra = {"retriever": build_retriever(backend)}
    except ImportError:
        extra = {}
    deps = SupervisorDeps(fast_llm=fast_llm, quality_llm=quality_llm, mcp=mcp,
                          session_store=store, version="v2", **extra)
    retriever = extra.get("retriever")
    graph = build_graph(deps)
    meta = {"label": args.label, "mode": args.mode, "backend": backend, "repeat": args.repeat,
            "fast_llm": fast_llm.name, "quality_llm": quality_llm.name, "git_rev": _git_rev(),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "runbook_classifier": f"rag({retriever.embedder.name})" if retriever else "keyword"}
    if args.mode == "chaos":
        meta.update({"chaos_rates": args.chaos_rates, "chaos_seed": args.chaos_seed})
    print(f"[eval] label={args.label} mode={args.mode} backend={backend} fast={fast_llm.name} "
          f"quality={quality_llm.name} rev={meta['git_rev']} items={len(dataset)} repeat={args.repeat} "
          f"runbook={meta['runbook_classifier']}")
    if backend != args.backend:
        print(f"[eval] 경고: 요청한 백엔드({args.backend})와 실제 백엔드({backend})가 다릅니다")

    # 워밍업 — MCP 클라이언트의 '프로세스 최초 1회 의도적 타임아웃'(Wave 9 데모)과
    # 모델 로딩 시간을 측정에서 제외한다.
    try:
        await _run_turn(graph, store, "auth-service 상태 확인해줘", "eval-warmup")
        print("[eval] 워밍업 완료")
    except Exception as e:
        print(f"[eval] 워밍업 실패: {type(e).__name__}: {e}")
    if args.mode == "chaos":   # 워밍업이 끝난 뒤에만 설치 — 측정하는 턴에만 장애를 건다
        chaos.install({"api.openai.com", "127.0.0.1"}, chaos.parse_rates(args.chaos_rates),
                      args.chaos_seed)
        print(f"[eval] 장애 주입 설치: {args.chaos_rates} seed={args.chaos_seed}")

    tag = datetime.now().strftime("%H%M%S")
    runs: list[dict] = []
    for rep in range(1, args.repeat + 1):
        for item in dataset:
            thread_id = f"eval-{args.label}-{tag}-{item['id']}-{rep}"
            error, result = None, None
            started = time.perf_counter()
            try:
                for setup in item.get("setup", []):   # 다턴 시나리오의 앞선 턴 (측정 제외)
                    await _run_turn(graph, store, setup, thread_id)
                CALLS.clear()
                if args.mode == "chaos":
                    chaos.begin(item["id"], rep)
                started = time.perf_counter()
                result = await _run_turn(graph, store, item["query"], thread_id)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                if args.mode == "normal":
                    traceback.print_exc(limit=2)
            elapsed = round(time.perf_counter() - started, 2)
            faults = chaos.end() if args.mode == "chaos" else []
            run = {"id": item["id"], "category": item["category"], "rep": rep, "faults": faults,
                   "success": result is not None and bool(result.get("final")),
                   "elapsed_s": elapsed, "error": error,
                   "llm_calls": len(CALLS), "llm_failed_calls": sum(not c["ok"] for c in CALLS),
                   "tokens": sum(c["tokens"] for c in CALLS), "llm_detail": list(CALLS),
                   **_score(item, result)}
            if result is not None:
                replan = next((e for e in result.get("events", [])
                               if e.get("type") == "ReplanCheck" and not e.get("is_sufficient")), {})
                run.update({"classifier": replan.get("classifier", "keyword" if replan else None),
                            "rag_score": replan.get("score"), "rag_margin": replan.get("margin"),
                            "embed_tokens": replan.get("embed_tokens", 0),
                            "degraded": len(result.get("degraded", [])),   # Before 코드에는 키가 없어 0
                            "degraded_stages": [d["stage"] for d in result.get("degraded", [])],
                            "retry_count": result.get("retry_count", 0),
                            "validation_attempts": result.get("validation_attempts", 0),
                            "replan_rounds": result.get("replan_rounds", 0),
                            "cost_usd_virtual": result.get("cost_usd", 0.0),
                            "reply": result.get("final", "")})
            runs.append(run)
            flags = " ".join(f"{k}={'O' if run[k] else 'X'}" for k in
                             ("route_ok", "targets_ok", "runbook_ok", "reply_ok") if k in run)
            print(f"[{rep}/{args.repeat}] {item['id']:<4} {elapsed:>6.1f}s "
                  f"{'OK ' if run['success'] else 'ERR'} calls={run['llm_calls']} "
                  f"tok={run['tokens']} {flags} {run.get('monitored', '')} {run.get('runbooks', '')}"
                  + (f" faults={[f['fault'] for f in faults]}" if faults else "")
                  + (f" degraded={run['degraded_stages']}" if run.get("degraded") else "")
                  + (f" {error[:120]}" if error else ""), flush=True)

    await mcp.stop()
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers
        wait_for_all_tracers()
    except Exception:
        pass

    overall = _summarize(runs)
    cats = list(dict.fromkeys(r["category"] for r in runs))
    by_cat = {c: _summarize([r for r in runs if r["category"] == c]) for c in cats}
    per_item = {}
    for item in dataset:
        rs = [r for r in runs if r["id"] == item["id"]]
        per_item[item["id"]] = {**_summarize(rs), "last_monitored": rs[-1].get("monitored", []),
                                "last_runbooks": rs[-1].get("runbooks", []),
                                "fault_names": [f["fault"] for r in rs for f in r["faults"]]}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.label}_{args.mode}_{backend}"
    (out / f"{stem}.json").write_text(json.dumps(
        {"meta": meta, "overall": overall, "by_category": by_cat, "per_item": per_item, "runs": runs},
        ensure_ascii=False, indent=1))
    (out / f"{stem}.md").write_text(_markdown(meta, overall, by_cat, per_item))
    print(f"\n[eval] 저장: {out / (stem + '.json')}, {out / (stem + '.md')}")
    print(json.dumps(overall, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
