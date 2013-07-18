

class Task(object):
    def __init__(self, function):
        self.function = function
        self.state = 'RUNNING'


class Taskpile(object):
    def __init__(self):
        self.queue = []

    def enqueue(self, task_function):
        self.queue.append(Task(task_function))
