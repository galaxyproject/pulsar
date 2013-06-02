from threading import Lock, Condition


class ConditionManager(object):

    def __init__(self):
        self.__conditions = dict()
        self.__conditions_count = dict()
        self.__conditions_lock = Lock()

    def acquire_condition(self, path):
        with self.__conditions_lock:
            if path in self.__conditions:
                condition = self.__conditions[path]
                cur_count = self.__conditions_count[path]
                self.__conditions_count[path] = cur_count + 1
            else:
                condition = Condition()
                self.__conditions[path] = condition
                self.__conditions_count[path] = 1
        return condition

    def release_condition(self, path):
        with self.__conditions_lock:
            cur_count = self.__conditions_count[path]
            self.__conditions_count[path] = cur_count - 1
            if cur_count == 0:
                del self.__conditions_count[path]
                del self.__conditions[path]


class ConditionHolder(object):

    def __init__(self, condition, path, condition_manager):
        self.condition = condition
        self.path = path
        self.condition_manager = condition_manager

    def __del__(self):
        self.condition_manager.release_condition(self.path)
