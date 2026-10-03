"""Container command descriptions shared by coexecution backends."""

from typing import (
    List,
    NamedTuple,
    Optional,
)


class CoexecutionContainerCommand(NamedTuple):
    image: str
    command: str
    args: List[str]
    working_directory: str
    ports: Optional[List[int]] = None
