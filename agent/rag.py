"""Runbook 선택 RAG — 키워드 규칙 대신 임베딩 유사도로 incident_type을 고른다.

baseline의 _classify_incident_type은 모니터링 alert 문구만 보고 키워드 목록 순서대로
매칭했다. 그래서
- 사용자가 말한 증상("타임아웃", "메모리 누수")을 전혀 보지 않았고
- alert가 없는 healthy 시스템(web-01)은 무조건 db-down으로 폴백했고
- 여러 시스템의 alert를 이어 붙이면 목록 앞쪽 키워드(cpu)가 이겼다

여기서는 runbook을 청크로 나눠 미리 임베딩해 두고(청크마다 incident_type 메타데이터),
"사용자 질의"와 "수집된 alert"를 각각 임베딩해 가중 합 유사도가 가장 높은 runbook을 고른다.
runbook 문서에는 한국어·영어 증상 키워드 한 줄(> 증상: …)을 보강해 두었다(데이터 보강).

임베딩 백엔드는 LLM 백엔드를 따른다: ollama → nomic-embed-text, openai → text-embedding-3-small.
RUNBOOK_CLASSIFIER=keyword로 기동하면 RAG 없이 baseline 규칙으로 동작한다 (Before/After 비교용).
"""
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from langsmith import traceable

from .errors import TIMEOUTS, retry_sync

RUNBOOK_DIR = Path(__file__).resolve().parent.parent / "data" / "runbooks"
OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embed"
OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"


class OllamaEmbedder:
    def __init__(self, model: str):
        self.name = f"ollama:{model}"
        self.model = model
        # nomic 계열은 질의/문서 접두어를 붙여야 검색 성능이 나온다
        self.prefix = ({"query": "search_query: ", "document": "search_document: "}
                       if "nomic" in model else {"query": "", "document": ""})

    def embed(self, texts: list[str], kind: str) -> tuple[list[list[float]], int]:
        payload = {"model": self.model, "input": [self.prefix[kind] + t for t in texts]}

        def attempt() -> dict:
            resp = httpx.post(OLLAMA_EMBED_URL, json=payload, timeout=TIMEOUTS["embed"])
            resp.raise_for_status()
            return resp.json()

        data, _ = retry_sync(attempt)
        return data["embeddings"], data.get("prompt_eval_count") or 0


class OpenAIEmbedder:
    def __init__(self, model: str):
        self.name = f"openai:{model}"
        self.model = model
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    def embed(self, texts: list[str], kind: str) -> tuple[list[list[float]], int]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "input": texts}

        def attempt() -> dict:
            resp = httpx.post(OPENAI_EMBED_URL, json=payload, headers=headers,
                              timeout=TIMEOUTS["embed"])
            resp.raise_for_status()
            return resp.json()

        data, _ = retry_sync(attempt)
        vectors = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
        return vectors, data.get("usage", {}).get("total_tokens", 0)


@dataclass
class Chunk:
    incident_type: str   # 메타데이터 — 검색 결과를 runbook 종류로 되돌리는 키
    text: str
    vector: list[float]


def _cosine(a: list[float], b: list[float]) -> float:
    """코사인 유사도 — 벡터 방향이 같을수록 1에 가깝다. 청크가 수십 개라 numpy 없이 계산한다."""
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return dot / norm if norm else 0.0


def split_runbook(text: str) -> list[str]:
    """runbook 1개 → 청크 목록: [제목 + 증상 키워드] + [제목 — 절차 n]…

    절차 줄마다 제목을 붙이는 이유: "로그 파일 정리" 같은 절차 문장만으로는 어떤 장애의
    절차인지 임베딩에 드러나지 않는다. 실험(16건)에서 문서 통째 임베딩보다 정확도가 높았다."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = lines[0].lstrip("# ") if lines else ""
    symptoms = [l.lstrip("> ") for l in lines[1:] if l.startswith(">")]
    steps = [re.sub(r"^\d+\.\s*", "", l) for l in lines[1:] if re.match(r"^\d+\.", l)]
    return ["\n".join([title, *symptoms])] + [f"{title} — {s}" for s in steps]


class RunbookRetriever:
    def __init__(self, embedder, runbook_dir: Path = RUNBOOK_DIR, query_weight: float = 0.8):
        self.embedder = embedder
        self.runbook_dir = runbook_dir
        self.query_weight = query_weight   # 사용자 질의 vs 수집된 alert 비중
        self.chunks: list[Chunk] = []
        self.index_tokens = 0

    def build(self) -> "RunbookRetriever":
        """서버 기동 시 1회 — 모든 runbook 청크를 임베딩해 메모리에 둔다 (Wave 1 싱글턴)."""
        pairs = [(p.stem, c) for p in sorted(self.runbook_dir.glob("*.md"))
                 for c in split_runbook(p.read_text())]
        vectors, self.index_tokens = self.embedder.embed([c for _, c in pairs], "document")
        self.chunks = [Chunk(t, c, v) for (t, c), v in zip(pairs, vectors)]
        return self

    @traceable(name="rag.classify_runbook")
    def classify(self, query: str, collected: list[dict]) -> dict:
        alerts = " ".join(
            f"{d['system_name']}: {'; '.join(d.get('alerts') or ['no alerts'])}"
            for d in (c["data"] for c in collected if c["source"] == "monitoring"))
        # 질의와 alert를 따로 임베딩한다 — 이어 붙이면 길이가 긴 alert 쪽으로 의미가 쏠린다
        texts = [query, alerts] if alerts else [query]
        vectors, tokens = self.embedder.embed(texts, "query")
        q_vec, a_vec = vectors[0], vectors[-1]
        # 사용자가 말한 증상을 우선(기본 0.8). alert가 없는 healthy 시스템이면 질의만 본다
        w = self.query_weight if alerts else 1.0
        scores: dict[str, float] = {}
        for ch in self.chunks:   # runbook별 점수 = 그 runbook 청크 중 최고 유사도
            s = w * _cosine(q_vec, ch.vector) + (1 - w) * _cosine(a_vec, ch.vector)
            scores[ch.incident_type] = max(s, scores.get(ch.incident_type, -1.0))
        ranking = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best, score = ranking[0]
        # 1·2위 점수 차 — 작을수록 판단이 불안정하다(nomic 실측 0.002~0.005, 한계 장표 근거)
        margin = score - ranking[1][1] if len(ranking) > 1 else score
        return {"incident_type": best, "score": round(score, 4), "margin": round(margin, 4),
                "ranking": [[t, round(s, 4)] for t, s in ranking[:3]], "embed_tokens": tokens}


def build_retriever(backend: str) -> RunbookRetriever | None:
    """LLM 백엔드에 맞는 임베딩으로 retriever를 만든다. keyword 모드·fake·실패 시 None."""
    if os.environ.get("RUNBOOK_CLASSIFIER", "rag") != "rag":
        return None
    if backend == "ollama":
        embedder = OllamaEmbedder(os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    elif backend == "openai":
        embedder = OpenAIEmbedder(os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small"))
    else:
        return None
    weight = float(os.environ.get("RAG_QUERY_WEIGHT", "0.8"))
    try:
        return RunbookRetriever(embedder, query_weight=weight).build()
    except Exception as exc:   # 인덱스를 못 만들면 키워드 규칙으로 동작 (서버 기동은 막지 않는다)
        print(f"[rag] runbook 인덱스 생성 실패 → 키워드 규칙 사용: {type(exc).__name__}: {exc}")
        return None
