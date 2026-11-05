import asyncio
import unittest
from typing import Optional, Sequence

from resilience import (
    ClientResponseError,
    LatencyBudgetExceeded,
    Response,
    RetryClient,
    RetryConfig,
    ServerResponseError,
    SubrequestSender,
)


class ScriptedSender(SubrequestSender):
    def __init__(self, outcomes: Sequence[Optional[Response]]) -> None:
        self._outcomes = outcomes
        self.calls = 0
        self.cancellations = 0

    async def send(self) -> Response:
        self.calls += 1
        outcome = self._outcomes[min(self.calls - 1, len(self._outcomes) - 1)]
        if outcome is not None:
            return outcome

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancellations += 1
            raise
        raise AssertionError("unreachable")


def make_config(**overrides) -> RetryConfig:
    values = {
        "max_retries": 5,
        "fast_errors_budget": 0,
        "failures_budget": 0,
        "timeout_budget": 0,
        "latency_budget": 1.0,
        "subrequest_latency_budget": 1.0,
    }
    values.update(overrides)
    return RetryConfig(**values)


class RetryClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_4xx_and_5xx_with_separate_budgets(self) -> None:
        expected = Response(status_code=200, body=b"ok")
        sender = ScriptedSender(
            [Response(status_code=429), Response(status_code=503), expected]
        )
        client = RetryClient(
            make_config(fast_errors_budget=1, failures_budget=1)
        )

        actual = await client.execute(sender)

        self.assertIs(actual, expected)
        self.assertEqual(sender.calls, 3)

    async def test_stops_when_error_budget_is_exhausted(self) -> None:
        cases = (
            (Response(status_code=400), ClientResponseError),
            (Response(status_code=500), ServerResponseError),
        )
        for response, error_type in cases:
            with self.subTest(status_code=response.status_code):
                sender = ScriptedSender([response, Response(status_code=200)])

                with self.assertRaises(error_type):
                    await RetryClient(make_config()).execute(sender)

                self.assertEqual(sender.calls, 1)

    async def test_stops_at_max_retries(self) -> None:
        sender = ScriptedSender(
            [Response(status_code=500), Response(status_code=500), Response(status_code=200)]
        )
        client = RetryClient(make_config(max_retries=2, failures_budget=2))

        with self.assertRaises(ServerResponseError):
            await client.execute(sender)

        self.assertEqual(sender.calls, 2)

    async def test_retries_timeout_and_cancels_subrequest(self) -> None:
        expected = Response(status_code=200)
        sender = ScriptedSender([None, expected])
        client = RetryClient(
            make_config(timeout_budget=1, subrequest_latency_budget=0.01)
        )

        actual = await client.execute(sender)

        self.assertIs(actual, expected)
        self.assertEqual(sender.calls, 2)
        self.assertEqual(sender.cancellations, 1)

    async def test_total_latency_budget_limits_all_subrequests(self) -> None:
        sender = ScriptedSender([None])
        client = RetryClient(
            make_config(
                max_retries=10,
                timeout_budget=10,
                latency_budget=0.03,
                subrequest_latency_budget=0.01,
            )
        )

        with self.assertRaises(LatencyBudgetExceeded) as context:
            await client.execute(sender)

        self.assertEqual(context.exception.latency_budget, 0.03)
        self.assertGreaterEqual(sender.calls, 2)
        self.assertEqual(sender.cancellations, sender.calls)


if __name__ == "__main__":
    unittest.main()
