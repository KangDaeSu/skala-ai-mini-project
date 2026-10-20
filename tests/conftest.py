import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LANGCHAIN_TRACING_V2"] = "false"   # 테스트 실행이 LangSmith로 전송되지 않게
os.environ["LANGSMITH_TRACING"] = "false"
