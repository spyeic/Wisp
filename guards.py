"""Small process-local guards, deliberately independent of API clients."""
from collections import OrderedDict, defaultdict, deque
import time


class Deduplicator:
    def __init__(self, max_entries=10000, ttl=86400, clock=time.monotonic):
        self.entries = OrderedDict()
        self.max_entries, self.ttl, self.clock = max_entries, ttl, clock

    def claim(self, key) -> bool:
        now = self.clock()
        while self.entries and now - next(iter(self.entries.values())) >= self.ttl:
            self.entries.popitem(last=False)
        if key in self.entries:
            return False
        self.entries[key] = now
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)
        return True


class RateLimiter:
    def __init__(self, limit: int, clock=time.monotonic):
        self.limit, self.clock = limit, clock
        self.requests = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = self.clock()
        queue = self.requests[user_id]
        while queue and now - queue[0] >= 60:
            queue.popleft()
        if len(queue) >= self.limit:
            return False
        queue.append(now)
        return True
