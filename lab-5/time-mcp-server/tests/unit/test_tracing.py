"""Unit tests for the Phoenix / OpenInference tracing bootstrap.

`tests/conftest.py` sets `PHOENIX_DISABLE_REGISTER=1` so the default test
path uses the no-op tracer. These tests explicitly clear that env var and
reload `core.server` so the real `phoenix.otel.register(...)` call runs
against a monkey-patched stub. The test asserts the production startup
hook would have invoked `register()` with `auto_instrument=True`, which is
what stitches client + server spans into a single Phoenix trace.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add src to Python path so `core.server` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def _reload_core_server():
    sys.modules.pop("core.server", None)
    sys.modules.pop("core", None)
    import core.server  # noqa: F401

    return importlib.import_module("core.server")


def test_bootstrap_calls_phoenix_register_with_auto_instrument(monkeypatch) -> None:
    """The non-test code path calls phoenix.otel.register(auto_instrument=True)."""
    monkeypatch.delenv("PHOENIX_DISABLE_REGISTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://test.example/v1/traces")
    monkeypatch.setenv("PHOENIX_PROJECT_NAME", "time-mcp-server")

    stub_provider = MagicMock(name="TracerProvider")
    stub_provider.get_tracer.return_value = MagicMock(name="Tracer")
    register_mock = MagicMock(name="register", return_value=stub_provider)

    import phoenix.otel  # noqa: F401  # ensure module is importable

    monkeypatch.setattr("phoenix.otel.register", register_mock)

    server_mod = _reload_core_server()

    register_mock.assert_called_once()
    kwargs = register_mock.call_args.kwargs
    assert kwargs.get("auto_instrument") is True
    assert kwargs.get("project_name") == "time-mcp-server"
    assert kwargs.get("endpoint") == "http://test.example/v1/traces"
    assert server_mod.TRACER_PROVIDER is stub_provider


def test_disabled_env_skips_register(monkeypatch) -> None:
    """With PHOENIX_DISABLE_REGISTER set, register() is not called and tracer
    is a no-op that still exposes the `.tool(...)` decorator API tools use."""
    monkeypatch.setenv("PHOENIX_DISABLE_REGISTER", "1")

    register_mock = MagicMock(name="register")
    monkeypatch.setattr("phoenix.otel.register", register_mock)

    server_mod = _reload_core_server()

    register_mock.assert_not_called()
    assert server_mod.TRACER_PROVIDER is None

    # The no-op tracer must keep `@tracer.tool(name=...)` working so tool
    # modules can be imported in tests without changing their source.
    decorator = server_mod.tracer.tool(name="MCP.test")
    sentinel = object()
    assert decorator(sentinel) is sentinel


def test_tools_are_wrapped_with_tracer_tool_decorator(monkeypatch) -> None:
    """Walk the FastMCP registry and assert each tool's span name is set."""
    monkeypatch.setenv("PHOENIX_DISABLE_REGISTER", "1")

    server_mod = _reload_core_server()
    from core.server import DynamicMCPServer  # type: ignore[import-not-found]

    server = DynamicMCPServer(name="Test", tools_dir="src/tools")
    server.load_tools()
    tools = server.get_tools_sync()
    assert {"get_current_time", "convert_time", "echo"} <= set(tools)
