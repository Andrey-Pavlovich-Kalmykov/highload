import asyncio
import unittest

from resilience import (
    CircuitBreakingConfig,
    CircuitBreakingMultiClient,
    CircuitOpenError,
    Response,
    RetryClient,
    SubrequestSender,
)
from test_retry import ScriptedSender
from test_round_robin import make_retry_config


class DelayedSender(SubrequestSender):
    def __init__(self, response: Response, delay: float) -> None:
        self._response = response
        self._delay = delay
        self.calls = 0

    async def send(self) -> Response:
        self.calls += 1
        await asyncio.sleep(self._delay)
        return self._response


def make_circuit_config(**overrides) -> CircuitBreakingConfig:
    values = {
        "window_size": 2,
        "error_rate_threshold": 0.5,
        "cooldown": 1.0,
    }
    values.update(overrides)
    return CircuitBreakingConfig(**values)


class CircuitBreakingMultiClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_skips_sender_after_error_rate_exceeds_threshold(self) -> None:
        expected = Response(status_code=200)
        senders = [
            ScriptedSender([Response(status_code=400), Response(status_code=500)]),
            ScriptedSender([Response(status_code=500), expected]),
        ]
        client = CircuitBreakingMultiClient(
            RetryClient(
                make_retry_config(
                    max_retries=4, fast_errors_budget=2, failures_budget=3
                )
            ),
            make_circuit_config(),
        )

        actual = await client.execute(senders)

        self.assertIs(actual, expected)
        self.assertEqual([sender.calls for sender in senders], [2, 2])

    async def test_fails_fast_when_all_circuits_are_open(self) -> None:
        senders = [
            ScriptedSender([Response(status_code=500)]),
            ScriptedSender([Response(status_code=500)]),
        ]
        client = CircuitBreakingMultiClient(
            RetryClient(make_retry_config()),
            make_circuit_config(window_size=1, error_rate_threshold=0),
        )

        with self.assertRaises(CircuitOpenError):
            await client.execute(senders)

        self.assertEqual([sender.calls for sender in senders], [1, 1])

    async def test_returns_sender_to_rotation_after_cooldown(self) -> None:
        expected = Response(status_code=200)
        senders = [
            ScriptedSender([Response(status_code=500), expected]),
            DelayedSender(Response(status_code=500), delay=0.02),
        ]
        client = CircuitBreakingMultiClient(
            RetryClient(
                make_retry_config(
                    max_retries=3,
                    failures_budget=2,
                    subrequest_latency_budget=0.1,
                )
            ),
            make_circuit_config(
                window_size=1, error_rate_threshold=0, cooldown=0.005
            ),
        )

        actual = await client.execute(senders)

        self.assertIs(actual, expected)
        self.assertEqual(senders[0].calls, 2)
        self.assertEqual(senders[1].calls, 1)

    async def test_timeout_counts_as_sender_error(self) -> None:
        expected = Response(status_code=200)
        senders = [ScriptedSender([None]), ScriptedSender([expected])]
        client = CircuitBreakingMultiClient(
            RetryClient(make_retry_config(timeout_budget=1)),
            make_circuit_config(window_size=1, error_rate_threshold=0),
        )

        actual = await client.execute(senders)

        self.assertIs(actual, expected)
        self.assertEqual([sender.calls for sender in senders], [1, 1])
        self.assertEqual(senders[0].cancellations, 1)

    async def test_rejects_empty_sender_list(self) -> None:
        client = CircuitBreakingMultiClient(
            RetryClient(make_retry_config()), make_circuit_config()
        )

        with self.assertRaises(ValueError):
            await client.execute([])


if __name__ == "__main__":
    unittest.main()
