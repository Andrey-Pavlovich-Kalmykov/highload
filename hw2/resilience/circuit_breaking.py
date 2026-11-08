import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Sequence

from resilience.config import CircuitBreakingConfig
from resilience.interfaces import ResilienceClient, SubrequestSender
from resilience.models import CircuitOpenError, Response
from resilience.round_robin import RoundRobinMultiClient


@dataclass
class _SenderState:
    sender: SubrequestSender
    outcomes: Deque[bool] = field(default_factory=deque)
    opened_until: Optional[float] = None


class _CircuitBreakingSender(SubrequestSender):
    def __init__(
        self,
        senders: Sequence[SubrequestSender],
        config: CircuitBreakingConfig,
    ) -> None:
        self._states = [_SenderState(sender) for sender in senders]
        self._config = config
        self._next_index = 0

    def _is_available(self, state: _SenderState, now: float) -> bool:
        if state.opened_until is None:
            return True
        if now < state.opened_until:
            return False
        state.opened_until = None
        state.outcomes.clear()
        return True

    def _select(self) -> _SenderState:
        now = asyncio.get_running_loop().time()
        for offset in range(len(self._states)):
            index = (self._next_index + offset) % len(self._states)
            state = self._states[index]
            if self._is_available(state, now):
                self._next_index = (index + 1) % len(self._states)
                return state
        raise CircuitOpenError

    def _record(self, state: _SenderState, success: bool) -> None:
        if len(state.outcomes) == self._config.window_size:
            state.outcomes.popleft()
        state.outcomes.append(success)
        if len(state.outcomes) < self._config.window_size:
            return

        errors = sum(not outcome for outcome in state.outcomes)
        error_rate = errors / self._config.window_size
        if error_rate > self._config.error_rate_threshold:
            state.opened_until = (
                asyncio.get_running_loop().time() + self._config.cooldown
            )

    async def send(self) -> Response:
        state = self._select()
        try:
            response = await state.sender.send()
        except asyncio.CancelledError:
            self._record(state, False)
            raise
        self._record(state, response.is_success)
        return response


class CircuitBreakingMultiClient(RoundRobinMultiClient):
    def __init__(
        self, strategy: ResilienceClient, config: CircuitBreakingConfig
    ) -> None:
        super().__init__(strategy)
        self._circuit_config = config

    def _create_sender(
        self, senders: Sequence[SubrequestSender]
    ) -> SubrequestSender:
        return _CircuitBreakingSender(senders, self._circuit_config)
