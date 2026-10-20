"""Wave 2 — MCP 서버 여러 개를 subprocess(stdio)로 1회씩 기동해 재사용하는 클라이언트.

Wave 1의 교훈대로 서버(lifespan)에서 한 번만 연결을 만들고 모든 요청이 공유한다.
Wave 9 데모용으로, 프로세스 최초의 get_monitoring_status 호출 1회는 일부러
asyncio.TimeoutError를 던진다(transient) — 재시도가 backoff 후 복구해야 한다.

연결 대상은 "ops"(mcp_server.py — monitoring tool + runbook resource + prompt, 실제
사용)와 "docs"(mcp_server_docs.py — API 문서 resource만 제공, agent는 사용하지 않는
decoy) 두 서버다. resource/prompt를 요청할 때는 어느 서버가 그걸 들고 있는지 미리
알고 있지 않다고 가정하고, find_resource_template()/find_prompt()로 연결된 서버들을
순서대로 조회(list)해 이름이 맞는 걸 찾은 뒤에야 그 서버로 read_resource/get_prompt를
보낸다.

세션 재연결 — MCP 서버 프로세스가 죽으면 baseline은 이후 모든 요청이 실패하거나 멈췄다
(서버를 재시작하기 전까지). stdio 세션은 AsyncExitStack으로 연 anyio 작업 그룹에 묶여 있어
"연 task에서만 닫을 수 있다". 그래서 연결을 소유하는 전용 백그라운드 task(_own_connections)를
두고, 요청 처리 중 세션이 끊긴 것을 감지하면 그 task에 재연결을 요청한 뒤 새 세션이 열릴 때까지
기다린다. 그다음 ConnectionError를 던져 resilience(graph의 _mcp)가 새 세션으로 다시 시도하게 한다.
"""
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import anyio
from langsmith import traceable
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:   # SDK 버전에 따라 이름이 다르다 (1.x McpError / 2.x MCPError)
    from mcp.shared.exceptions import McpError as _MCPError
except ImportError:
    from mcp.shared.exceptions import MCPError as _MCPError

SERVER_DIR = Path(__file__).parent.parent
DEFAULT_SERVER_SCRIPTS = {
    "ops": SERVER_DIR / "mcp_server.py",
    "docs": SERVER_DIR / "mcp_server_docs.py",
}

_CLOSED = (anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream,
           BrokenPipeError, ConnectionResetError)


def _session_dead(exc: BaseException) -> bool:
    """세션이 끊겨서 난 실패인가 — 프로세스 종료·파이프 끊김 (도구 자체의 에러와 구분)."""
    if isinstance(exc, _CLOSED):
        return True
    return isinstance(exc, _MCPError) and "closed" in str(exc).lower()


def _attr(obj, *names):
    """mcp SDK 버전에 따라 pydantic 필드명이 camelCase(예: resourceTemplates,
    uriTemplate, 구버전 1.x)와 snake_case(예: resource_templates, uri_template,
    신버전 2.x)로 갈린다 — 이 프로젝트 안에도 시스템 python3(mcp 1.28.1, camelCase)와
    .venv(mcp 2.2.0, snake_case)가 섞여 있어 실행 환경마다 바뀐다. 둘 다 시도해서
    설치된 버전과 무관하게 동작하게 한다."""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AttributeError(f"{type(obj).__name__!r} has none of {names!r}")


class MCPClient:
    def __init__(self, flaky_first_tool_call: bool = True,
                 server_scripts: dict[str, Path] | None = None):
        self._server_scripts = server_scripts or DEFAULT_SERVER_SCRIPTS
        self.sessions: dict[str, ClientSession] = {}
        self._lock = asyncio.Lock()
        self._flaky_pending = flaky_first_tool_call   # Wave 9 시뮬레이션
        self._owner: asyncio.Task | None = None   # 연결을 열고 닫는 유일한 task
        self._wake = asyncio.Event()              # 재연결·종료 요청 신호
        self._closing = False
        self._start_error: BaseException | None = None
        self.generation = 0    # 세션을 새로 열 때마다 1 증가 — 같은 끊김에 재연결이 겹치지 않게
        self.reconnects = 0

    # ── 연결 소유 task ──────────────────────────────────────────────────
    async def _open(self, stack: AsyncExitStack) -> dict[str, ClientSession]:
        sessions = {}
        for server_name, script in self._server_scripts.items():
            params = StdioServerParameters(
                command=sys.executable, args=[str(script)],
                env={**os.environ, "FASTMCP_LOG_LEVEL": "ERROR"})
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            sessions[server_name] = session
        return sessions

    async def _own_connections(self) -> None:
        """세션 한 세대마다 새 자식 task를 띄우고, 그 task가 끝나면(재연결 요청) 다음 세대를 연다.

        세대마다 task를 새로 만드는 이유(실측): 죽은 프로세스의 stdio 작업 그룹을 닫으면 anyio가
        건 취소 상태가 그 task에 남아, 같은 task에서 다음 세션을 열 때 CancelledError로 터진다.
        끝난 자식 task와 함께 그 상태도 버린다."""
        while not self._closing:
            opened_before = self.generation
            conn = asyncio.create_task(self._one_connection())
            await asyncio.wait({conn})            # 자식이 어떻게 끝나든(취소 포함) 예외를 받지 않는다
            if self._start_error is not None or self._closing:
                return
            if self.generation == opened_before:  # 이번 세대는 열지도 못했다 — 잠시 뒤 다시
                await asyncio.sleep(1.0)
            self.reconnects += 1

    async def _one_connection(self) -> None:
        """세션 열기 → 재연결·종료 요청 대기 → 같은 task에서 닫기."""
        stack = AsyncExitStack()
        try:
            sessions = await self._open(stack)
        except Exception as exc:
            if self.generation == 0:              # 최초 기동 실패는 start()로 알린다
                self._start_error = exc
            await self._close_quietly(stack)
            return
        self.sessions = sessions
        self.generation += 1
        await self._wake.wait()
        self._wake.clear()
        self.sessions = {}
        await self._close_quietly(stack)

    @staticmethod
    async def _close_quietly(stack: AsyncExitStack, timeout: float = 5.0) -> None:
        # 이미 죽은 프로세스를 정리하면서 나는 에러·지연은 무시한다. asyncio.wait_for는 aclose를
        # 별도 task로 감싸 "다른 task에서 cancel scope 종료" 오류가 나므로(실측), 같은 task 안에서
        # 시간 제한을 거는 anyio.move_on_after를 쓴다.
        try:
            with anyio.move_on_after(timeout):
                await stack.aclose()
        except asyncio.CancelledError:
            # 죽은 프로세스의 stdio 작업 그룹을 닫을 때 그 그룹의 취소가 새어 나온다(실측).
            # 이 task가 정말 바깥에서 취소된 경우(서버 종료)에만 다시 던진다.
            if asyncio.current_task().cancelling():
                raise
        except Exception:
            pass

    async def start(self) -> None:
        self._owner = asyncio.create_task(self._own_connections())
        while self.generation == 0 and not self._owner.done():
            await asyncio.sleep(0.05)
        if self._start_error is not None:
            raise self._start_error

    async def stop(self) -> None:
        if self._owner is not None:
            self._closing = True
            self._wake.set()
            await self._owner
            self._owner = None

    async def _reconnect(self, seen_generation: int, timeout: float = 15.0) -> None:
        """seen_generation 세션이 끊겼다 — 아직 아무도 재연결을 요청하지 않았으면 요청하고,
        새 세션(다음 generation)이 열릴 때까지 기다린다."""
        if self.generation == seen_generation:
            self._wake.set()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self.generation == seen_generation:
            if loop.time() > deadline:
                raise ConnectionError("MCP 재연결 시간 초과")
            await asyncio.sleep(0.05)

    async def _use(self, server: str, op):
        """세션 1회 사용 — 세션이 끊겨 있으면 재연결하고 ConnectionError로 재시도를 요청한다."""
        generation = self.generation
        if server not in self.sessions:
            raise ConnectionError(f"MCP 세션 없음({server}) — 재연결 중")
        try:
            async with self._lock:
                return await op(self.sessions[server])
        except Exception as exc:
            if not _session_dead(exc):
                raise
            await self._reconnect(generation)
            raise ConnectionError(
                f"MCP 세션이 끊겨 재연결함 (누적 {self.reconnects}회) — 재시도 필요") from exc

    # ── MCP 호출 ────────────────────────────────────────────────────────
    @traceable(run_type="tool", name="mcp.call_tool")
    async def call_tool(self, name: str, arguments: dict, server: str = "ops") -> dict:
        if self._flaky_pending and name == "get_monitoring_status":
            self._flaky_pending = False
            raise asyncio.TimeoutError("simulated transient timeout (Wave 9 demo)")
        result = await self._use(server, lambda s: s.call_tool(name, arguments))
        return json.loads(result.content[0].text)

    @traceable(run_type="tool", name="mcp.list_resource_templates")
    async def list_resource_templates(self, server: str) -> list:
        result = await self._use(server, lambda s: s.list_resource_templates())
        return _attr(result, "resourceTemplates", "resource_templates")

    @traceable(run_type="tool", name="mcp.find_resource_template")
    async def find_resource_template(self, template_name: str) -> tuple[str, str]:
        """연결된 서버들을 순서대로 조회해 template_name을 제공하는 서버를 찾는다."""
        for server_name in list(self._server_scripts):
            templates = await self.list_resource_templates(server_name)
            matched = next((t for t in templates if t.name == template_name), None)
            if matched is not None:
                return server_name, _attr(matched, "uriTemplate", "uri_template")
        raise ValueError(
            f"MCP resource template not found on any connected server: {template_name}")

    @traceable(run_type="tool", name="mcp.read_resource")
    async def read_resource(self, uri: str, server: str) -> str:
        result = await self._use(server, lambda s: s.read_resource(uri))
        return result.contents[0].text

    @traceable(run_type="tool", name="mcp.list_prompts")
    async def list_prompts(self, server: str) -> list:
        result = await self._use(server, lambda s: s.list_prompts())
        return result.prompts

    @traceable(run_type="tool", name="mcp.find_prompt")
    async def find_prompt(self, prompt_name: str) -> str:
        """연결된 서버들을 순서대로 조회해 prompt_name을 제공하는 서버를 찾는다."""
        for server_name in list(self._server_scripts):
            prompts = await self.list_prompts(server_name)
            if any(p.name == prompt_name for p in prompts):
                return server_name
        raise ValueError(
            f"MCP prompt not found on any connected server: {prompt_name}")

    @traceable(run_type="tool", name="mcp.get_prompt")
    async def get_prompt(self, name: str, arguments: dict, server: str = "ops") -> str:
        result = await self._use(server, lambda s: s.get_prompt(name, arguments))
        return result.messages[0].content.text
