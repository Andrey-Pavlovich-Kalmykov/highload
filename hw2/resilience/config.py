import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DefaultConfig:
    latency_budget: float
    max_retries: int = 1

    def __post_init__(self) -> None:
        if self.max_retries != 1:
            raise ValueError("default strategy supports exactly one subrequest")
        if not math.isfinite(self.latency_budget) or self.latency_budget <= 0:
            raise ValueError("latency_budget must be a positive finite number")
