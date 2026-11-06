"""Host integration contracts; common GUI Test code owns no Dashboard objects."""
from typing import Protocol


class DashboardPort(Protocol):
    def pin(self, job_id: str, connection: dict) -> dict: ...

    def validate(self, link: dict) -> None: ...

    def submit(self, run: dict) -> dict: ...
