import math
from dataclasses import dataclass


def _validate_latency(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")


def _validate_integer(name: str, value: int, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer greater than or equal to {minimum}")


@dataclass(frozen=True)
class DefaultConfig:
    latency_budget: float
    max_retries: int = 1

    def __post_init__(self) -> None:
        if self.max_retries != 1:
            raise ValueError("default strategy supports exactly one subrequest")
        _validate_latency("latency_budget", self.latency_budget)


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int
    fast_errors_budget: int
    failures_budget: int
    timeout_budget: int
    latency_budget: float
    subrequest_latency_budget: float

    def __post_init__(self) -> None:
        _validate_integer("max_retries", self.max_retries, 1)
        _validate_integer("fast_errors_budget", self.fast_errors_budget, 0)
        _validate_integer("failures_budget", self.failures_budget, 0)
        _validate_integer("timeout_budget", self.timeout_budget, 0)
        _validate_latency("latency_budget", self.latency_budget)
        _validate_latency(
            "subrequest_latency_budget", self.subrequest_latency_budget
        )


@dataclass(frozen=True)
class ExponentialBackoffRetryConfig(RetryConfig):
    initial_backoff: float
    max_backoff: float
    backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_latency("initial_backoff", self.initial_backoff)
        _validate_latency("max_backoff", self.max_backoff)
        if self.max_backoff < self.initial_backoff:
            raise ValueError("max_backoff must be greater than or equal to initial_backoff")
        if not math.isfinite(self.backoff_multiplier) or self.backoff_multiplier <= 1:
            raise ValueError("backoff_multiplier must be finite and greater than 1")
