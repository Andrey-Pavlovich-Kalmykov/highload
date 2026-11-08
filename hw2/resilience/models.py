from dataclasses import dataclass


@dataclass(frozen=True)
class Response:
    status_code: int
    body: bytes = b""

    def __post_init__(self) -> None:
        if not 200 <= self.status_code <= 599:
            raise ValueError("status_code must be in the 200...599 range")

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        return 500 <= self.status_code < 600


class RequestError(Exception):
    pass


class HttpResponseError(RequestError):
    def __init__(self, response: Response) -> None:
        self.response = response
        super().__init__(f"request failed with HTTP {response.status_code}")


class ClientResponseError(HttpResponseError):
    pass


class ServerResponseError(HttpResponseError):
    pass


class LatencyBudgetExceeded(RequestError):
    def __init__(self, latency_budget: float) -> None:
        self.latency_budget = latency_budget
        super().__init__(f"latency budget of {latency_budget} seconds exhausted")


class CircuitOpenError(RequestError):
    def __init__(self) -> None:
        super().__init__("all senders are temporarily unavailable")
