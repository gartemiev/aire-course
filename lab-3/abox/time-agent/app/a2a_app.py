# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A2A entrypoint for kagent BYO mode.

Serve with:
    uvicorn app.a2a_app:a2a_app --host 0.0.0.0 --port 8080

We use ADK's AgentCardBuilder directly (instead of letting to_a2a()
auto-build) for one reason: to_a2a()'s builder defaults
capabilities.streaming to None, which the A2A SDK treats as False, which
breaks the kagent UI's message/stream calls. The builder itself accepts
a capabilities= kwarg — to_a2a() just doesn't forward it. So we call the
builder ourselves with streaming=True and pass the finished card to
to_a2a(). Skills are still auto-discovered from the MCPToolset, so adding
a new tool in agent.py shows up here automatically.

Side effect: the MCP server must be reachable at pod startup, because
the builder enumerates MCP tools to populate skills. If MCP is down,
the pod fails to start (CrashLoopBackOff) instead of starting and then
failing every tool call — which is what we want.
"""

import asyncio
import os

from a2a.types import AgentCapabilities
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from app.agent import root_agent

PORT = int(os.getenv("PORT", "8080"))
A2A_PUBLIC_URL = os.getenv("A2A_PUBLIC_URL", f"http://0.0.0.0:{PORT}/")


async def _build_agent_card():
    return await AgentCardBuilder(
        agent=root_agent,
        rpc_url=A2A_PUBLIC_URL,
        capabilities=AgentCapabilities(streaming=True),
    ).build()


agent_card = asyncio.run(_build_agent_card())

a2a_app = to_a2a(root_agent, port=PORT, agent_card=agent_card)
