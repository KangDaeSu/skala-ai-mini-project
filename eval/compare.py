"""Before/After 비교표 — output/의 평가 결과 JSON을 합쳐 보고서용 마크다운을 만든다.

실행 (프로젝트 루트에서):
    .venv/bin/python3 eval/compare.py
결과:
    output/final_comparison.md

정상 모드 Before는 before_normal_openai(16건) + before-runbook_normal_openai(5단계에서 추가한
runbook 케이스 5건, 같은 before 태그 코드로 측정)를 합친다. 장애 주입은 Before와 같은 16건·같은
seed로 측정한 결과끼리 비교한다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
sys.path.insert(0, str(ROOT / "eval"))

from run_eval import _summarize   # 평가 스크립트와 같은 집계 함수를 쓴다


def _load(*names: str) -> tuple[list[dict], list[dict]]:
    runs, metas = [], []
    for name in names:
        data = json.loads((OUT / f"{name}.json").read_text())
        runs += data["runs"]
        metas.append(data["meta"])
    return runs, metas


def _row(label: str, key: str, before: dict, after: dict) -> str:
    return f"| {label} | {before.get(key, '-')} | {after.get(key, '-')} |"


def _cost_tokens(runs: list[dict]) -> int:
    return sum(r["tokens"] + r.get("embed_tokens", 0) for r in runs)


def main() -> None:
    b_norm, b_meta = _load("before_normal_openai", "before-runbook_normal_openai")
    a_norm, a_meta = _load("after_normal_openai")
    b_chaos, _ = _load("before_chaos_openai")
    a_chaos, a_chaos_meta = _load("after_chaos_openai")
    bn, an = _summarize(b_norm), _summarize(a_norm)
    bc, ac = _summarize(b_chaos), _summarize(a_chaos)
    cat = lambda runs, c: _summarize([r for r in runs if r["category"] == c])

    lines = [
        "# 최종 Before / After 비교 (OpenAI)", "",
        f"- 모델: fast=`{a_meta[0]['fast_llm']}`, quality=`{a_meta[0]['quality_llm']}`",
        f"- Before 커밋 `{b_meta[0]['git_rev']}` (runbook 선택: keyword) · "
        f"After 커밋 정상 `{a_meta[0]['git_rev']}` · 장애 주입 `{a_chaos_meta[0]['git_rev']}` "
        f"(runbook 선택: `{a_meta[0].get('runbook_classifier')}`)",
        f"- 정상 모드: 21건 × 3회 · 장애 주입: 16건 × 2회, `{a_chaos_meta[0].get('chaos_rates')}` "
        f"seed={a_chaos_meta[0].get('chaos_seed')} (Before와 동일)", "",
        "## 1. 장애 주입 모드 — 신뢰성", "",
        "| 지표 | Before | After |", "|---|---|---|",
        _row("주입된 장애 수", "faults_injected", bc, ac),
        _row("장애를 맞은 실행 수", "faulted_runs", bc, ac),
        _row("**성공률**", "success", bc, ac),
        _row("**장애를 맞은 실행의 성공률**", "success_when_faulted", bc, ac),
        _row("대체 동작(규칙·템플릿)이 일어난 실행", "degraded_runs", bc, ac),
        _row("지연 p50 (초, 성공한 실행)", "latency_p50", bc, ac),
        _row("**최대 지연 (초, 실패 포함)**", "latency_max_all", bc, ac),
        "", "## 2. 정상 모드 — 품질 (회귀 검사 포함)", "",
        "| 지표 | Before | After |", "|---|---|---|",
        _row("성공률", "success", bn, an),
        _row("route 정확도", "route_acc", bn, an),
        _row("**조사 대상 정확도**", "target_acc", bn, an),
        f"| └ 모니터링 밖 시스템 (unknown-system) | {cat(b_norm, 'unknown-system')['target_acc']} "
        f"| {cat(a_norm, 'unknown-system')['target_acc']} |",
        _row("**runbook 선택 정확도**", "runbook_acc", bn, an),
        f"| └ 증상·alert가 엇갈리는 케이스 (runbook) | {cat(b_norm, 'runbook')['runbook_acc']} "
        f"| {cat(a_norm, 'runbook')['runbook_acc']} |",
        _row("지연 p50 (초)", "latency_p50", bn, an),
        _row("지연 p95 (초)", "latency_p95", bn, an),
        _row("지연 최대 (초)", "latency_max", bn, an),
        _row("평균 LLM 호출 수", "avg_llm_calls", bn, an),
        _row("평균 LLM 토큰", "avg_tokens", bn, an),
        f"| 총 토큰 (LLM + 임베딩) | {_cost_tokens(b_norm):,} | {_cost_tokens(a_norm):,} |",
        "", "## 3. 쿼리별 — 정상 모드 (마지막 반복 기준)", "",
        "| id | Before 조사 대상 → runbook | After 조사 대상 → runbook | Before p50(s) | After p50(s) |",
        "|---|---|---|---|---|",
    ]
    for qid in dict.fromkeys(r["id"] for r in a_norm):
        b = [r for r in b_norm if r["id"] == qid]
        a = [r for r in a_norm if r["id"] == qid]
        fmt = lambda r: (f"{', '.join(r.get('monitored', [])) or '-'} → "
                         f"{', '.join(r.get('runbooks', [])) or '-'}"
                         + ("" if "targets_ok" not in r else (" ✅" if r["targets_ok"] and r.get("runbook_ok", True) else " ❌")))
        lines.append(f"| {qid} | {fmt(b[-1]) if b else '-'} | {fmt(a[-1])} | "
                     f"{_summarize(b)['latency_p50'] if b else '-'} | {_summarize(a)['latency_p50']} |")
    (OUT / "final_comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
