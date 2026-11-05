from resilience.config import ExponentialBackoffRetryConfig
from resilience.models import ClientResponseError, RequestError
from resilience.retry import RetryClient


class ExponentialBackoffRetryClient(RetryClient):
    def __init__(self, config: ExponentialBackoffRetryConfig) -> None:
        super().__init__(config)
        self._backoff_config = config

    def _retry_delay(
        self, error: RequestError, failures: int, timeouts: int
    ) -> float:
        if isinstance(error, ClientResponseError):
            return 0

        exponent = failures + timeouts - 1
        try:
            delay = self._backoff_config.initial_backoff * (
                self._backoff_config.backoff_multiplier ** exponent
            )
        except OverflowError:
            return self._backoff_config.max_backoff
        return min(delay, self._backoff_config.max_backoff)
