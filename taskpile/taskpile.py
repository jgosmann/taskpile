import patch_multiprocessing
from multiprocessing import Manager, Process, Value
import os
import signal
import time


assert patch_multiprocessing  # suppress unused warning


class State(object):
    PENDING = 0
    RUNNING = 1
    FINISHED = 2
    STOPPED = 3


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


class QueueManager(object):
    def __init__(self):
        self._data_manager = Manager()
        self.pending = self._data_manager.list()
        self.running = self._data_manager.list()
        self.finished = self._data_manager.list()

    def enqueue(self, task):
        self.pending.append(task)

    def start_next(self):
        try:
            task = self.pending.pop()
            task.start()
            self.running.append(task)
        except IndexError:
            raise self.Empty()

    class Empty(Exception):
        pass


class TaskManager(object):
    pass


class Taskpile(object):
    pass
    #def __init__(self, task_manager=TaskManager()):
        #self.queues = QueueManager()
        ##self._task_manager = Process(
            ##target=self._manage_tasks, args=(self.queues,))
        ##self._task_manager.start()

    #def enqueue(self, task_function):
        #self.queues.enqueue(Task(task_function))

    #@staticmethod
    #def _manage_tasks(queue_manager):
        #while True:
            #try:
                #queue_manager.start_next()
            #except QueueManager.Empty:
                #time.sleep(1)

        #while not exit_event.is_set():
            #try:
                #task = .pop()
                #task.start()
                ## TODO finished
            #except Queue.Empty:
                #pass
            #notifier.wait()
            #notifier.clear()
