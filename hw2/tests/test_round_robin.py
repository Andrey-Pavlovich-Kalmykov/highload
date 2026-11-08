import unittest
from unittest.mock import AsyncMock, patch

from resilience import (
    ExponentialBackoffRetryClient,
    Response,
    RetryClient,
    RetryConfig,
    RoundRobinMultiClient,
    ServerResponseError,
)
from test_backoff import make_config as make_backoff_config
from test_retry import ScriptedSender


def make_retry_config(**overrides) -> RetryConfig:
    values = {
        "max_retries": 5,
        "fast_errors_budget": 0,
        "failures_budget": 5,
        "timeout_budget": 5,
        "latency_budget": 1.0,
        "subrequest_latency_budget": 0.01,
    }
    values.update(overrides)
    return RetryConfig(**values)


class RoundRobinMultiClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_rotates_senders_on_every_subrequest(self) -> None:
        expected = Response(status_code=200)
        senders = [
            ScriptedSender([Response(status_code=500)]),
            ScriptedSender([Response(status_code=502)]),
            ScriptedSender([expected]),
        ]
        client = RoundRobinMultiClient(
            RetryClient(make_retry_config(max_retries=3, failures_budget=2))
        )

        actual = await client.execute(senders)

        self.assertIs(actual, expected)
        self.assertEqual([sender.calls for sender in senders], [1, 1, 1])

    async def test_wraps_around_sender_list(self) -> None:
        expected = Response(status_code=200)
        senders = [
            ScriptedSender([Response(status_code=500), Response(status_code=500)]),
            ScriptedSender([Response(status_code=500), expected]),
        ]
        client = RoundRobinMultiClient(
            RetryClient(make_retry_config(max_retries=4, failures_budget=3))
        )

        actual = await client.execute(senders)

        self.assertIs(actual, expected)
        self.assertEqual([sender.calls for sender in senders], [2, 2])

    async def test_preserves_retry_budgets_across_senders(self) -> None:
        senders = [
            ScriptedSender([Response(status_code=500)]),
            ScriptedSender([Response(status_code=500)]),
            ScriptedSender([Response(status_code=200)]),
        ]
        client = RoundRobinMultiClient(
            RetryClient(make_retry_config(failures_budget=1))
        )

        with self.assertRaises(ServerResponseError):
            await client.execute(senders)

        self.assertEqual([sender.calls for sender in senders], [1, 1, 0])

    async def test_composes_with_exponential_backoff_strategy(self) -> None:
        expected = Response(status_code=200)
        senders = [
            ScriptedSender([Response(status_code=500)]),
            ScriptedSender([expected]),
        ]
        client = RoundRobinMultiClient(
            ExponentialBackoffRetryClient(make_backoff_config())
        )

        with patch("resilience.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
            actual = await client.execute(senders)

        self.assertIs(actual, expected)
        self.assertEqual([sender.calls for sender in senders], [1, 1])
        sleep.assert_awaited_once_with(0.01)

    async def test_rejects_empty_sender_list(self) -> None:
        client = RoundRobinMultiClient(RetryClient(make_retry_config()))

        with self.assertRaises(ValueError):
            await client.execute([])


if __name__ == "__main__":
    unittest.main()
