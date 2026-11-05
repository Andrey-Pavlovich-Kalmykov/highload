import asyncio
from typing import Optional

from resilience.config import DefaultConfig, RetryConfig
from resilience.default import DefaultClient
from resilience.interfaces import ResilienceClient, SubrequestSender
from resilience.models import (
    ClientResponseError,
    LatencyBudgetExceeded,
    RequestError,
    Response,
    ServerResponseError,
)


class RetryClient(ResilienceClient):
    def __init__(self, config: RetryConfig) -> None:
        self._config = config

    async def execute(self, sender: SubrequestSender) -> Response:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._config.latency_budget
        fast_errors = 0
        failures = 0
        timeouts = 0
        last_error: Optional[RequestError] = None

        for _ in range(self._config.max_retries):
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise LatencyBudgetExceeded(self._config.latency_budget) from last_error

            attempt_timeout = min(
                remaining, self._config.subrequest_latency_budget
            )
            try:
                return await DefaultClient(
                    DefaultConfig(latency_budget=attempt_timeout)
                ).execute(sender)
            except ClientResponseError as error:
                fast_errors += 1
                if fast_errors > self._config.fast_errors_budget:
                    raise
                last_error = error
            except ServerResponseError as error:
                failures += 1
                if failures > self._config.failures_budget:
                    raise
                last_error = error
            except LatencyBudgetExceeded as error:
                if loop.time() >= deadline:
                    raise LatencyBudgetExceeded(
                        self._config.latency_budget
                    ) from error
                timeouts += 1
                if timeouts > self._config.timeout_budget:
                    raise
                last_error = error

        assert last_error is not None
        raise last_error
