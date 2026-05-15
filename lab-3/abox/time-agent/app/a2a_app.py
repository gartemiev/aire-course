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

Agent card is exposed at /.well-known/agent-card.json. We build it
explicitly (rather than letting to_a2a() auto-generate) so we can declare
capabilities.streaming=True — the kagent UI uses A2A's message/stream
endpoint, which the auto-generated card disables by default.
"""

import os

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from app.agent import root_agent

PORT = int(os.getenv("PORT", "8080"))
A2A_PUBLIC_URL = os.getenv("A2A_PUBLIC_URL", f"http://0.0.0.0:{PORT}/")

agent_card = AgentCard(
    name="root_agent",
    description="Agent that answers time and timezone questions using the time MCP server.",
    url=A2A_PUBLIC_URL,
    version=os.getenv("AGENT_VERSION", "0.1.0"),
    protocol_version="0.2.6",
    capabilities=AgentCapabilities(streaming=True),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="get_current_time",
            name="get_current_time",
            description="Return the current time, date, and weekday for an IANA timezone (default UTC).",
            tags=["time", "mcp"],
        ),
        AgentSkill(
            id="convert_time",
            name="convert_time",
            description="Convert an ISO datetime between two IANA timezones.",
            tags=["time", "mcp"],
        ),
    ],
    supports_authenticated_extended_card=False,
)

a2a_app = to_a2a(root_agent, port=PORT, agent_card=agent_card)
