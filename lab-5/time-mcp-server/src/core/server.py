"""Dynamic MCP server implementation with automatic tool discovery.

This server automatically discovers and loads tools from the tools directory.
Each tool file should contain a function decorated with @mcp.tool().
"""

import asyncio
import importlib.util
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import phoenix.otel
from dotenv import load_dotenv
from fastmcp import FastMCP

from .utils import load_config

logger = logging.getLogger(__name__)

# Global FastMCP instance for tools to import
mcp: FastMCP = FastMCP(name="Dynamic Server")


# --- Phoenix / OpenInference tracing bootstrap -------------------------------
#
# Runs at module import so tool files can `from core.server import tracer`
# and wrap their handlers with `@tracer.tool(name="MCP.<tool>")`. The
# decorator emits an OpenInference-flavoured tool span around every
# invocation; combined with `auto_instrument=True` on `register()`, the
# server side of the trace lands in Phoenix without further plumbing.
#
# Tests set `PHOENIX_DISABLE_REGISTER=1` (see tests/conftest.py) to swap in
# a no-op tracer that preserves the decorator API but never opens an OTLP
# connection. tests/unit/test_tracing.py clears that env var and reloads
# this module to assert `phoenix.otel.register` was called with
# `auto_instrument=True`.
PROJECT_NAME = os.environ.get("PHOENIX_PROJECT_NAME", "time-mcp-server")


class _NoOpToolDecorator:
    def __call__(self, fn):  # type: ignore[no-untyped-def]
        return fn


class _NoOpTracer:
    """Drop-in tracer for tests; keeps the `@tracer.tool(...)` API callable."""

    def tool(self, name: str | None = None, **kwargs: Any) -> _NoOpToolDecorator:
        return _NoOpToolDecorator()

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        yield None


if os.environ.get("PHOENIX_DISABLE_REGISTER"):
    TRACER_PROVIDER: Any = None
    tracer: Any = _NoOpTracer()
else:
    TRACER_PROVIDER = phoenix.otel.register(
        project_name=PROJECT_NAME,
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
        auto_instrument=True,
    )
    tracer = TRACER_PROVIDER.get_tracer("time-mcp-server")


class DynamicMCPServer:
    """MCP server with dynamic tool loading capabilities."""

    def __init__(self, name: str, tools_dir: str = "src/tools"):
        """Initialize the dynamic MCP server.

        Args:
            name: Server name
            tools_dir: Directory containing tool files
        """
        global mcp
        self.name = name
        self.tools_dir = Path(tools_dir)
        self.config = self._load_config()

        # Load local environment variables if configured
        self._load_local_env()

        # Update global FastMCP instance
        mcp = FastMCP(name=self.name)
        self.mcp = mcp

        # Track loaded tools
        self.loaded_tools: list[str] = []

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from kmcp.yaml."""
        return load_config("kmcp.yaml")

    def _load_local_env(self) -> None:
        """Load environment variables from a .env file if it exists."""
        # load_dotenv will search for a .env file and load it.
        # It does not fail if the file is not found.
        if load_dotenv(override=True):
            logger.info("Loaded environment variables from .env file")

    def load_tools(self) -> None:
        """Discover and load all tools from the tools directory.

        Raises:
            RuntimeError: if any tool file fails to import or registers no
                tools. Caller (main.py) catches this and exits non-zero so
                the server fails fast on bad tool definitions.
        """
        if not self.tools_dir.exists():
            logger.warning("Tools directory %s does not exist", self.tools_dir)
            return

        # Find all Python files in tools directory
        tool_files = list(self.tools_dir.glob("*.py"))
        tool_files = [f for f in tool_files if f.name != "__init__.py"]

        if not tool_files:
            logger.warning("No tool files found in %s", self.tools_dir)
            return

        loaded_count = 0
        has_errors = False

        for tool_file in tool_files:
            try:
                # Get the number of tools before importing
                tools_before = len(asyncio.run(self.mcp.list_tools()))

                # Simply import the module - tools auto-register via @mcp.tool()
                # decorator
                tool_name = tool_file.stem
                if self._import_tool_module(tool_file, tool_name):
                    # Check if any tools were actually registered
                    tools_after = len(asyncio.run(self.mcp.list_tools()))
                    if tools_after > tools_before:
                        self.loaded_tools.append(tool_name)
                        loaded_count += 1
                        logger.info("Loaded tool module: %s", tool_name)
                    else:
                        logger.error(
                            "Tool file %s did not register any tools", tool_name
                        )
                        has_errors = True
                else:
                    logger.error("Failed to load tool module: %s", tool_name)
                    has_errors = True

            except Exception as e:
                logger.error("Error loading tool %s: %s", tool_file.name, e)
                has_errors = True

        # Fail fast - if any tool fails to load, stop the server
        if has_errors:
            raise RuntimeError(
                f"One or more tools in {self.tools_dir} failed to load"
            )

        logger.info("📦 Successfully loaded %d tools", loaded_count)

        if loaded_count == 0:
            logger.warning("No tools loaded. Server starting without tools.")

    def _import_tool_module(self, tool_file: Path, tool_name: str) -> bool:
        """Import a tool module, which auto-registers tools via decorators.

        Args:
            tool_file: Path to the tool file
            tool_name: Name of the tool (same as filename)

        Returns:
            True if module was imported successfully
        """
        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(tool_name, tool_file)
            if spec is None or spec.loader is None:
                return False

            module = importlib.util.module_from_spec(spec)

            # Add to sys.modules so it can be imported by other modules
            sys.modules[f"tools.{tool_name}"] = module

            # Execute the module - this will trigger @mcp.tool() decorators
            spec.loader.exec_module(module)

            return True

        except Exception as e:
            logger.error("Error importing %s: %s", tool_file, e)
            return False

    def get_tools_sync(self) -> dict[str, Any]:
        """Get tools synchronously for testing purposes."""
        # This is a simplified version for testing - in real usage, use get_tools()
        # async
        tools_list = asyncio.run(self.mcp.list_tools())
        return {t.name: t for t in tools_list}

    def run(self, transport_mode: str = "stdio", host: str = "localhost", port: int = 3000) -> None:
        """Run the FastMCP server.

        Args:
            transport_mode: Transport mode - "stdio", or "http"
            host: Host to bind to in HTTP mode
            port: Port to bind to in HTTP mode
        """

        if transport_mode == "http":
            self.mcp.run(transport="http", host=host, port=port, path="/mcp")
        elif transport_mode == "stdio":
            # Default to stdio mode
            self.mcp.run()
