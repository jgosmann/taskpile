import patch_multiprocessing
from multiprocessing import Process, Value
import os
import signal


assert patch_multiprocessing  # suppress unused warning


class State(object):
    PENDING = 0
    RUNNING = 1
    FINISHED = 2
    STOPPED = 3

    @staticmethod
    def is_valid_state(state):
        return 0 <= state and state < 4


class Task(object):
    def __init__(self, function, args=(), name=None):
        self.function = function
        self.args = args
        if name is None:
            self.name = function.__name__
        else:
            self.name = name
        self._exitcode = None
        self._pid = None
        self._state = Value('H', State.PENDING)

    exitcode = property(lambda self: self._exitcode)
    pid = property(lambda self: self._pid)
    state = property(lambda self: self._state.value)

    def start(self):
        process = Process(
            target=self.__run,
            args=(self._state, self.function) + self.args)
        process.start()
        self._pid = process.pid

    @staticmethod
    def __run(state_var, function, *args):
        state_var.value = State.RUNNING
        try:
            function(*args)
        finally:
            state_var.value = State.FINISHED

    def stop(self):
        os.kill(self.pid, signal.SIGSTOP)
        self._state.value = State.STOPPED

    def cont(self):
        os.kill(self.pid, signal.SIGCONT)
        self._state.value = State.RUNNING

    def join(self):
        opid, self._exitcode = os.waitpid(self.pid, 0)

    def terminate(self):
        os.kill(self.pid, signal.SIGTERM)
        self._state.value = State.FINISHED


class Taskpile(object):
    def __init__(self, max_parallel=1):
        self.pending = []
        self.running = []
        self.finished = []
        self.max_parallel = max_parallel

    def enqueue(self, task):
        self.pending.append(task)

    def update(self):
        self._update_queues()
        self._manage_tasks()

    def _update_queues(self):
        pending = []
        running = []
        stopped = []
        for task in self.pending + self.running:
            state = int(task.state)
            assert State.is_valid_state(state)
            if state == State.PENDING:
                pending.append(task)
            elif state == State.RUNNING:
                running.append(task)
            elif state == State.FINISHED:
                self.finished.append(task)
            elif state == State.STOPPED:
                stopped.append(task)
        self.pending = stopped + pending
        self.running = running

    def _manage_tasks(self):
        while len(self.running) > self.max_parallel:
            task = self.running.pop()
            task.stop()
            self.pending.insert(0, task)
        while len(self.pending) > 0 and len(self.running) < self.max_parallel:
            task = self.pending.pop(0)
            if task.state == State.STOPPED:
                task.cont()
            else:
                task.start()
            self.running.append(task)
