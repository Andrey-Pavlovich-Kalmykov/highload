import asyncio

from resilience.config import DefaultConfig
from resilience.interfaces import ResilienceClient, SubrequestSender
from resilience.models import (
    ClientResponseError,
    LatencyBudgetExceeded,
    Response,
    ServerResponseError,
)


class DefaultClient(ResilienceClient):
    def __init__(self, config: DefaultConfig) -> None:
        self._config = config

    async def execute(self, sender: SubrequestSender) -> Response:
        try:
            response = await asyncio.wait_for(
                sender.send(), timeout=self._config.latency_budget
            )
        except asyncio.TimeoutError as error:
            raise LatencyBudgetExceeded(self._config.latency_budget) from error

        if response.is_success:
            return response
        if response.is_client_error:
            raise ClientResponseError(response)
        raise ServerResponseError(response)
