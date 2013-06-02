from threading import Lock, Event


class TransferEventManager(object):

    def __init__(self):
        self.events = dict()
        self.events_lock = Lock()

    def acquire_event(self, path, force_clear=False):
        with self.events_lock:
            if path in self.events:
                event_holder = self.events[path]
            else:
                event_holder = EventHolder(Event(), path, self)
                self.events[path] = event_holder
        if force_clear:
            event_holder.event.clear()
        return event_holder

    def free_event(self, path):
        with self.events_lock:
            del self.events[path]


class EventHolder(object):

    def __init__(self, event, path, condition_manager):
        self.event = event
        self.path = path
        self.condition_manager = condition_manager

    def release(self):
        self.event.set()

    def __del__(self):
        self.condition_manager.free_event(self.path)
