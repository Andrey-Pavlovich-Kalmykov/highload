from abc import ABC, abstractmethod
from typing import Sequence

from resilience.models import Response


class SubrequestSender(ABC):
    @abstractmethod
    async def send(self) -> Response:
        raise NotImplementedError


class ResilienceClient(ABC):
    @abstractmethod
    async def execute(self, sender: SubrequestSender) -> Response:
        raise NotImplementedError


class MultiResilienceClient(ABC):
    @abstractmethod
    async def execute(self, senders: Sequence[SubrequestSender]) -> Response:
        raise NotImplementedError
