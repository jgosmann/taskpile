from __future__ import absolute_import

import errno
from multiprocessing import cpu_count, Process, Value
import os
import signal
import sys
import subprocess
import string
from tempfile import mkstemp, TemporaryFile


try:
    from taskpile import _patch_multiprocessing
except:
    import _patch_multiprocessing
from taskpile.sanitize import quote_for_shell
from taskpile.taskspec import TaskGroupSpec


assert _patch_multiprocessing  # suppress unused warning


class State(object):
    PENDING = 0
    RUNNING = 1
    FINISHED = 2
    STOPPED = 3

    @staticmethod
    def is_valid_state(state):
        return 0 <= state and state < 4


class Task(object):
    def __init__(self, function, args=(), kwargs={}, name=None, niceness=0):
        self.function = function
        self.args = args
        self.kwargs = kwargs
        if name is None:
            self.name = function.__name__
        else:
            self.name = name
        self.niceness = niceness
        self._exitcode = None
        self._exitsignal = None
        self._pid = None
        self._state = Value('H', State.PENDING)

    exitcode = property(lambda self: self._exitcode)
    exitsignal = property(lambda self: self._exitsignal)
    pid = property(lambda self: self._pid)
    state = property(lambda self: self._state.value)

    def start(self):
        process = Process(
            target=self.__run,
            args=(self._state, self.niceness, self.function) + self.args,
            kwargs=self.kwargs)
        try:
            process.start()
        except OSError as err:
            if err.errno != errno.EDEADLK:
                raise err
        else:
            self._pid = process.pid

    @staticmethod
    def __run(state_var, niceness, function, *args, **kwargs):
        state_var.value = State.RUNNING
        os.nice(niceness)
        try:
            retval = function(*args, **kwargs)
            try:
                exitcode = int(retval)
            except:
                exitcode = 0
        finally:
            state_var.value = State.FINISHED
        sys.exit(exitcode)

    def stop(self):
        os.kill(self.pid, signal.SIGSTOP)
        self._state.value = State.STOPPED

    def cont(self):
        os.kill(self.pid, signal.SIGCONT)
        self._state.value = State.RUNNING

    def join(self):
        if self.pid is not None:
            opid, exit_status_indication = os.waitpid(self.pid, 0)
            self._exitsignal = exit_status_indication & 0xff
            self._exitcode = exit_status_indication >> 8

    def terminate(self):
        if self.pid is not None:
            os.kill(self.pid, signal.SIGTERM)
        self._state.value = State.FINISHED


class TemplateFileFormatter(string.Formatter):
    def __init__(self, task_spec):
        super(TemplateFileFormatter, self).__init__()
        self.task_spec = task_spec
        self.original_files = {}

    def parse(self, format_string):
        for literal_text, field_name, format_spec, conversion in super(
                TemplateFileFormatter, self).parse(format_string):
            if conversion is not None and conversion is not 't':
                if format_spec != '':
                    format_spec = ':' + format_spec
                literal_text = '{}{{{}!{}{}}}'.format(
                    literal_text, field_name, conversion, format_spec)
                field_name = format_spec = conversion = None
            yield literal_text, field_name, format_spec, conversion

    def convert_field(self, value, conversion):
        if conversion != 't':
            return super(TemplateFileFormatter, self).convert_field(
                value, conversion)

        fd, new_filename = mkstemp()
        try:
            self.original_files[new_filename] = value
            with open(value, 'r') as template:
                for line in template:
                    os.write(fd, line.format(**self.task_spec))
        finally:
            os.close(fd)
        return quote_for_shell(new_filename)


class ExternalTask(Task):
    # FIXME remove original_files from core ExternalTask as it is only needed
    # for the UI
    def __init__(self, command, name=None, original_files={}, niceness=0):
        if name is None:
            name = command
        self.command = command
        self.original_files = original_files
        self.outbuf, self.errbuf = (TemporaryFile('w+'), TemporaryFile('w+'))
        super(ExternalTask, self).__init__(
            subprocess.call, (command,), {
                'shell': True, 'stdout': self.outbuf, 'stderr': self.errbuf},
            name, niceness=niceness)

    @classmethod
    def from_task_spec(cls, spec, niceness=0):
        name = spec.get(TaskGroupSpec.NAME_KEY, None)
        formatter = TemplateFileFormatter(spec)
        cmd = formatter.format(spec[TaskGroupSpec.CMD_KEY], **spec)
        return ExternalTask(cmd, name, original_files=formatter.original_files)


class Taskpile(object):
    def __init__(self, max_parallel=max(1, cpu_count() - 1)):
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
                task.join()
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
        # Start at most one process at once. Otherwise, we can easily run
        # in race conditions in the programs started and alike.
        # There also seems to be a race condition in Python itself.
        if len(self.pending) > 0 and len(self.running) < self.max_parallel:
            task = self.pending.pop(0)
            if task.state == State.STOPPED:
                task.cont()
            else:
                task.start()
            self.running.append(task)
