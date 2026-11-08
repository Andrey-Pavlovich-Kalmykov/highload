import unittest
from unittest.mock import AsyncMock, call, patch

from resilience import (
    ExponentialBackoffRetryClient,
    ExponentialBackoffRetryConfig,
    LatencyBudgetExceeded,
    Response,
)
from test_retry import ScriptedSender


def make_config(**overrides) -> ExponentialBackoffRetryConfig:
    values = {
        "max_retries": 5,
        "fast_errors_budget": 0,
        "failures_budget": 5,
        "timeout_budget": 5,
        "latency_budget": 1.0,
        "subrequest_latency_budget": 0.01,
        "initial_backoff": 0.01,
        "max_backoff": 0.1,
        "backoff_multiplier": 2.0,
    }
    values.update(overrides)
    return ExponentialBackoffRetryConfig(**values)


class ExponentialBackoffRetryClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_waits_before_retry_after_5xx(self) -> None:
        expected = Response(status_code=200)
        sender = ScriptedSender([Response(status_code=500), expected])
        client = ExponentialBackoffRetryClient(make_config())

        with patch("resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            actual = await client.execute(sender)

        self.assertIs(actual, expected)
        sleep.assert_awaited_once_with(0.01)

    async def test_does_not_wait_before_retry_after_4xx(self) -> None:
        expected = Response(status_code=200)
        sender = ScriptedSender([Response(status_code=400), expected])
        client = ExponentialBackoffRetryClient(make_config(fast_errors_budget=1))

        with patch("resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            actual = await client.execute(sender)

        self.assertIs(actual, expected)
        sleep.assert_not_awaited()

    async def test_increases_delay_exponentially_up_to_limit(self) -> None:
        sender = ScriptedSender(
            [
                Response(status_code=500),
                Response(status_code=500),
                Response(status_code=500),
                Response(status_code=200),
            ]
        )
        client = ExponentialBackoffRetryClient(make_config(max_backoff=0.015))

        with patch("resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await client.execute(sender)

        self.assertEqual(
            sleep.await_args_list, [call(0.01), call(0.015), call(0.015)]
        )

    async def test_waits_before_retry_after_timeout(self) -> None:
        expected = Response(status_code=200)
        sender = ScriptedSender([None, expected])
        client = ExponentialBackoffRetryClient(make_config(initial_backoff=0.02))

        with patch("resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            actual = await client.execute(sender)

        self.assertIs(actual, expected)
        sleep.assert_awaited_once_with(0.02)
        self.assertEqual(sender.cancellations, 1)

    async def test_backoff_is_bounded_by_total_latency_budget(self) -> None:
        sender = ScriptedSender([Response(status_code=500), Response(status_code=200)])
        client = ExponentialBackoffRetryClient(
            make_config(
                latency_budget=0.02,
                initial_backoff=0.05,
                max_backoff=0.05,
            )
        )

        with self.assertRaises(LatencyBudgetExceeded) as context:
            await client.execute(sender)

        self.assertEqual(context.exception.latency_budget, 0.02)
        self.assertEqual(sender.calls, 1)


if __name__ == "__main__":
    unittest.main()
