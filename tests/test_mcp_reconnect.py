"""MCP 세션 재연결 — 실제 MCP 서버 프로세스를 강제 종료하고 다음 호출이 살아나는지 본다 (통합 테스트, 약 3초)."""
import asyncio
import os
import signal
import subprocess

from agent.mcp_client import MCPClient
from agent.resilience import call_async, guard


def _kill_mcp_servers() -> list[str]:
    pids = subprocess.run(["pgrep", "-P", str(os.getpid()), "-f", "mcp_server"],
                          capture_output=True, text=True).stdout.split()
    for pid in pids:
        os.kill(int(pid), signal.SIGKILL)
    return pids


def test_session_is_reconnected_after_mcp_server_dies():
    async def scenario():
        mcp = MCPClient(flaky_first_tool_call=False)
        await mcp.start()
        call = lambda: guard(call_async, "mcp", lambda t: asyncio.wait_for(
            mcp.call_tool("get_monitoring_status", {"system_name": "web-01"}), t))
        try:
            assert (await call()).ok
            assert _kill_mcp_servers()          # ops·docs 서버 프로세스를 SIGKILL
            await asyncio.sleep(0.3)
            result = await call()               # 끊김 감지 → 재연결 → 재시도로 성공
            return result, mcp.reconnects, mcp.generation
        finally:
            await mcp.stop()

    result, reconnects, generation = asyncio.run(scenario())
    assert result.ok, result.error
    assert result.value[0]["system_name"] == "web-01"
    assert result.value[1] >= 1                 # 재시도로 복구됐다
    assert (reconnects, generation) == (1, 2)
