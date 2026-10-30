"""Application-facing chat boundary. No ADK, model or tool imports here."""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal, Protocol

@dataclass(frozen=True)
class GatewayRequest:
    session_id: str
    request_id: str
    text: str
    ledger: dict
    locale: str = 'en'

@dataclass
class GatewayResult:
    status: Literal['success', 'needs_clarification', 'partial_failure']
    reply: str
    ledger: dict
    committed_activity_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)

class AgentGateway(Protocol):
    @property
    def configured(self) -> bool: ...
    async def run(self, request: GatewayRequest) -> GatewayResult: ...
    async def erase(self, session_id: str) -> None: ...

class MockGateway:
    """Explicit development adapter; never infers or mutates real activities."""
    configured = True

    async def run(self, request: GatewayRequest) -> GatewayResult:
        return GatewayResult(status='needs_clarification',
            reply='Mock chat adapter: use manual activity entry. No activities were calculated or saved.',
            ledger=deepcopy(request.ledger), warnings=['Development mock; no model was called.'])

    async def erase(self, session_id: str) -> None:
        pass
