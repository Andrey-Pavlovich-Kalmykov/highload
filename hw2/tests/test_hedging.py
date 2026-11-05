import unittest

from resilience import (
    HedgingConfig,
    HedgingMultiClient,
    LatencyBudgetExceeded,
    Response,
)
from test_retry import ScriptedSender


class HedgingMultiClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_first_successful_response_prevents_hedging(self) -> None:
        expected = Response(status_code=200)
        senders = [
            ScriptedSender([expected]),
            ScriptedSender([Response(status_code=200)]),
            ScriptedSender([Response(status_code=200)]),
        ]
        client = HedgingMultiClient(
            HedgingConfig(latency_budget=0.1, hedging_delay=0.01)
        )

        actual = await client.execute(senders)

        self.assertIs(actual, expected)
        self.assertEqual([sender.calls for sender in senders], [1, 0, 0])

    async def test_hedges_all_remaining_senders_and_cancels_losers(self) -> None:
        expected = Response(status_code=200)
        senders = [
            ScriptedSender([None]),
            ScriptedSender([expected]),
            ScriptedSender([None]),
        ]
        client = HedgingMultiClient(
            HedgingConfig(latency_budget=0.1, hedging_delay=0.005)
        )

        actual = await client.execute(senders)

        self.assertIs(actual, expected)
        self.assertEqual([sender.calls for sender in senders], [1, 1, 1])
        self.assertEqual(senders[0].cancellations, 1)
        self.assertEqual(senders[2].cancellations, 1)

    async def test_fast_error_response_does_not_trigger_hedging(self) -> None:
        senders = [
            ScriptedSender([Response(status_code=500)]),
            ScriptedSender([Response(status_code=200)]),
        ]
        client = HedgingMultiClient(
            HedgingConfig(latency_budget=0.02, hedging_delay=0.01)
        )

        with self.assertRaises(LatencyBudgetExceeded) as context:
            await client.execute(senders)

        self.assertEqual(context.exception.latency_budget, 0.02)
        self.assertEqual([sender.calls for sender in senders], [1, 0])

    async def test_latency_budget_cancels_all_subrequests(self) -> None:
        senders = [ScriptedSender([None]) for _ in range(3)]
        client = HedgingMultiClient(
            HedgingConfig(latency_budget=0.02, hedging_delay=0.005)
        )

        with self.assertRaises(LatencyBudgetExceeded) as context:
            await client.execute(senders)

        self.assertEqual(context.exception.latency_budget, 0.02)
        self.assertEqual([sender.calls for sender in senders], [1, 1, 1])
        self.assertEqual(
            [sender.cancellations for sender in senders], [1, 1, 1]
        )

    async def test_rejects_empty_sender_list(self) -> None:
        client = HedgingMultiClient(
            HedgingConfig(latency_budget=0.1, hedging_delay=0.01)
        )

        with self.assertRaises(ValueError):
            await client.execute([])


if __name__ == "__main__":
    unittest.main()
