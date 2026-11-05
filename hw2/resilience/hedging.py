import asyncio
from typing import Sequence

from resilience.config import DefaultConfig, HedgingConfig
from resilience.default import DefaultClient
from resilience.interfaces import MultiResilienceClient, SubrequestSender
from resilience.models import (
    HttpResponseError,
    LatencyBudgetExceeded,
    Response,
)


class HedgingMultiClient(MultiResilienceClient):
    def __init__(self, config: HedgingConfig) -> None:
        self._config = config

    async def _execute_subrequest(
        self, sender: SubrequestSender, deadline: float
    ) -> Response:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise LatencyBudgetExceeded(self._config.latency_budget)
        return await DefaultClient(DefaultConfig(latency_budget=remaining)).execute(
            sender
        )

    async def execute(self, senders: Sequence[SubrequestSender]) -> Response:
        if not senders:
            raise ValueError("at least one sender is required")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._config.latency_budget
        tasks = {
            asyncio.create_task(self._execute_subrequest(senders[0], deadline))
        }

        try:
            if len(senders) > 1:
                remaining = deadline - loop.time()
                done, _ = await asyncio.wait(
                    tasks,
                    timeout=min(self._config.hedging_delay, max(remaining, 0)),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done and loop.time() < deadline:
                    tasks.update(
                        asyncio.create_task(
                            self._execute_subrequest(sender, deadline)
                        )
                        for sender in senders[1:]
                    )

            while tasks:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise LatencyBudgetExceeded(self._config.latency_budget)

                done, _ = await asyncio.wait(
                    tasks,
                    timeout=remaining,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    raise LatencyBudgetExceeded(self._config.latency_budget)

                tasks.difference_update(done)
                for task in done:
                    try:
                        return task.result()
                    except HttpResponseError:
                        continue
                    except LatencyBudgetExceeded as error:
                        raise LatencyBudgetExceeded(
                            self._config.latency_budget
                        ) from error

            remaining = deadline - loop.time()
            if remaining > 0:
                await asyncio.sleep(remaining)
            raise LatencyBudgetExceeded(self._config.latency_budget)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
