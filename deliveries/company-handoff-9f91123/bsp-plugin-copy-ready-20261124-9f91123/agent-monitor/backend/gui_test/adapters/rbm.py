from typing import Protocol


class BoardDirectory(Protocol):
    """Read-only directory; registration is owned by the existing RBC client."""
    def boards(self) -> list[dict]: ...
    def verify(self, connection: dict, dual: bool) -> None: ...
