from typing import Sequence

from resilience.interfaces import (
    MultiResilienceClient,
    ResilienceClient,
    SubrequestSender,
)
from resilience.models import Response


class _RoundRobinSender(SubrequestSender):
    def __init__(self, senders: Sequence[SubrequestSender]) -> None:
        self._senders = tuple(senders)
        self._next_index = 0

    async def send(self) -> Response:
        sender = self._senders[self._next_index]
        self._next_index = (self._next_index + 1) % len(self._senders)
        return await sender.send()


class RoundRobinMultiClient(MultiResilienceClient):
    def __init__(self, strategy: ResilienceClient) -> None:
        self._strategy = strategy

    async def execute(self, senders: Sequence[SubrequestSender]) -> Response:
        if not senders:
            raise ValueError("at least one sender is required")
        return await self._strategy.execute(_RoundRobinSender(senders))
