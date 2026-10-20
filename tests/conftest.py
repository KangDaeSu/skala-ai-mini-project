import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LANGCHAIN_TRACING_V2"] = "false"   # 테스트 실행이 LangSmith로 전송되지 않게
os.environ["LANGSMITH_TRACING"] = "false"
os.environ.setdefault("LLM_RETRY_BASE_DELAY", "0.01")   # 재시도 대기를 짧게 — 테스트 시간 단축


@pytest.fixture(autouse=True)
def _fresh_circuit_breakers():
    """서킷 브레이커는 프로세스 전역 상태다 — 테스트끼리 차단 상태가 새지 않게 매번 초기화."""
    from agent.resilience import reset_breakers
    reset_breakers()
    yield
    reset_breakers()
