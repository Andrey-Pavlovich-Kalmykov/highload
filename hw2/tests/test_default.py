import asyncio
import unittest

from resilience import (
    ClientResponseError,
    DefaultClient,
    DefaultConfig,
    LatencyBudgetExceeded,
    Response,
    ServerResponseError,
    SubrequestSender,
)


class StubSender(SubrequestSender):
    def __init__(self, response: Response) -> None:
        self._response = response
        self.calls = 0

    async def send(self) -> Response:
        self.calls += 1
        return self._response


class HangingSender(SubrequestSender):
    def __init__(self) -> None:
        self.calls = 0
        self.cancelled = asyncio.Event()

    async def send(self) -> Response:
        self.calls += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("unreachable")


class DefaultClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_successful_response_after_one_subrequest(self) -> None:
        expected = Response(status_code=201, body=b"created")
        sender = StubSender(expected)

        actual = await DefaultClient(DefaultConfig(latency_budget=1)).execute(sender)

        self.assertIs(actual, expected)
        self.assertEqual(sender.calls, 1)

    async def test_raises_client_error_for_4xx(self) -> None:
        sender = StubSender(Response(status_code=404, body=b"not found"))

        with self.assertRaises(ClientResponseError) as context:
            await DefaultClient(DefaultConfig(latency_budget=1)).execute(sender)

        self.assertEqual(context.exception.response.status_code, 404)
        self.assertEqual(sender.calls, 1)

    async def test_raises_server_error_for_5xx(self) -> None:
        sender = StubSender(Response(status_code=503))

        with self.assertRaises(ServerResponseError) as context:
            await DefaultClient(DefaultConfig(latency_budget=1)).execute(sender)

        self.assertEqual(context.exception.response.status_code, 503)
        self.assertEqual(sender.calls, 1)

    async def test_timeout_cancels_subrequest(self) -> None:
        sender = HangingSender()

        with self.assertRaises(LatencyBudgetExceeded):
            await DefaultClient(DefaultConfig(latency_budget=0.01)).execute(sender)

        self.assertEqual(sender.calls, 1)
        self.assertTrue(sender.cancelled.is_set())

    def test_validates_default_strategy_parameters(self) -> None:
        with self.assertRaises(ValueError):
            DefaultConfig(latency_budget=1, max_retries=2)
        with self.assertRaises(ValueError):
            DefaultConfig(latency_budget=0)
        with self.assertRaises(ValueError):
            DefaultConfig(latency_budget=float("inf"))


if __name__ == "__main__":
    unittest.main()
