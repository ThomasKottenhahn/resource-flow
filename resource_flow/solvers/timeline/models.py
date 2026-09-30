from dataclasses import dataclass
from datetime import datetime

from ...models import Process

@dataclass
class ScheduledTask:
    """Represents a scheduled execution of a process."""
    process: Process
    scale: float
    start_time: datetime
    end_time: datetime
    location: str

@dataclass
class ScheduleEvent:
    """Represents an event in the timeline (e.g. travel, waiting, or a process execution)."""
    name: str
    start_time: datetime
    end_time: datetime
    location: str
    description: str
