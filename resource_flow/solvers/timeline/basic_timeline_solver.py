from ...dag import DAG
from ...models import Query, TimelineSchedule
from ..interfaces import TimelineSolver

class BasicTimelineSolver(TimelineSolver):
    def solve(self) -> TimelineSchedule:
        # Stub implementation
        return TimelineSchedule(process_times={})
