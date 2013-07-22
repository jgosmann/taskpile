from functools import wraps
from multiprocessing import Pipe, Process
from multiprocessing.reduction import reduce_connection
import pickle
import time

from hamcrest import assert_that, contains, described_as, \
    greater_than_or_equal_to, is_, is_not
try:
    from unittest.mock import patch, MagicMock
except:
    from mock import patch, MagicMock

from taskpile import State, Task, Taskpile


def run_in_process(connection, function, *args, **kwargs):
    try:
        retval = function(*args, **kwargs)
    except Exception as err:
        connection.send((None, err))
    else:
        connection.send((retval, None))
    finally:
        connection.close()


def timelimit(timeout):
    def wrap(function):
        @wraps(function)
        def timelimited_wrapper(*args, **kwargs):
            parent_conn, child_conn = Pipe(False)
            process = Process(
                target=run_in_process, args=(child_conn, function) + args,
                kwargs=kwargs)
            process.start()
            process.join(timeout)
            if process.is_alive():
                process.terminate()
                raise TimeoutError()
            else:
                retval, err = parent_conn.recv()
                if err is None:
                    return retval
                else:
                    raise err
        return timelimited_wrapper
    return wrap


class TimeoutError(Exception):
    pass


def noop():
    pass


def raise_exception():
    raise Exception()


def wait_for_data_in_pipe(pickled_reduced_pipe):
    func, args = pickle.loads(pickled_reduced_pipe)
    pipe = func(*args)
    pipe.send('started')
    pipe.recv()
    pipe.close()


class DummyTaskController(object):
    def __init__(self):
        self.__parent_pipe, self.__child_pipe = Pipe()

    def create_task(self):
        return Task(
            wait_for_data_in_pipe,
            (pickle.dumps(reduce_connection(self.__child_pipe)),))

    def is_started(self, timeout=0):
        return self.__parent_pipe.poll(timeout)

    def wait_until_started_or_fail(self, timeout=5):
        assert_that(
            self.is_started(timeout), described_as(
                'Task started within %0 seconds.', is_(True), timeout))

    def finish(self):
        self.__parent_pipe.send('arbitrary data to cause exit')
        self.__parent_pipe.close()


class MockTask(MagicMock):
    instances_created = 0

    def __init__(self, mock_id=None):
        MagicMock.__init__(self)
        if mock_id is None:
            self.id = self.instances_created
            self.instances_created += 1
        else:
            self.id = mock_id

        self.__eq__ = lambda self, other: self.id == other.id
        self.__reduce__ = lambda self: (MockTask, (self.id,))

    def _get_child_mock(self, **kwargs):
        return MagicMock(**kwargs)


class TestTask(object):
    def test_is_initially_pending(self):
        task = Task(noop)
        assert_that(task.state, is_(State.PENDING))

    def test_stores_function_and_args(self):
        task = Task(noop, (1, 2))
        assert_that(task.function, is_(noop))
        assert_that(task.args, contains(1, 2))

    def test_pid_is_initially_none(self):
        task = Task(noop)
        assert_that(task.pid, is_(None))

    def test_start_sets_pid(self):
        task = Task(noop)
        task.start()
        assert_that(task.pid, is_(greater_than_or_equal_to(0)))

    def test_start_sets_state_to_running(self):
        task_ctrl = DummyTaskController()
        task = task_ctrl.create_task()
        task.start()
        task_ctrl.wait_until_started_or_fail()
        try:
            assert_that(task.state, is_(State.RUNNING))
        finally:
            task_ctrl.finish()

    @timelimit(1)
    def test_updates_state_after_finishing(self):
        task_ctrl = DummyTaskController()
        task = task_ctrl.create_task()
        task.start()
        task_ctrl.finish()
        task.join()
        assert_that(task.state, is_(State.FINISHED))

    def test_exitcode_is_initially_none(self):
        task = Task(noop)
        assert_that(task.exitcode, is_(None))

    def test_exitcode_set_after_process_finished(self):
        task = Task(noop)
        task.start()
        task.join()
        assert_that(task.exitcode, is_(0))

    def test_exitcode_after_exception_is_not_zero(self):
        task = Task(raise_exception)
        with patch('sys.stderr'):
            task.start()
            task.join()
        assert_that(task.exitcode, is_not(0))

    def test_state_after_exception_is_finished(self):
        task = Task(raise_exception)
        with patch('sys.stderr'):
            task.start()
            task.join()
        assert_that(task.state, is_(State.FINISHED))

    @timelimit(1)
    def test_can_terminate_task(self):
        task_ctrl = DummyTaskController()
        task = task_ctrl.create_task()
        task.start()
        task_ctrl.wait_until_started_or_fail()
        task.terminate()
        task.join()
        assert_that(task.state, is_(State.FINISHED))
        assert_that(task.exitcode, is_not(0))

    @timelimit(1)
    def test_can_stop_and_continue_task(self):
        task_ctrl = DummyTaskController()
        task = task_ctrl.create_task()
        task.start()
        task_ctrl.wait_until_started_or_fail()
        task.stop()
        task_ctrl.finish()
        # Wait for the process (0.2s should suffice) to finish in case it gets
        # not stopped. In theory this does not resolve the raise condition,
        # but I cannot think of a better solution. Worst case would be that
        # this test passes when it should fail, but it will always pass when
        # it is ought to pass.
        time.sleep(0.2)
        assert_that(task.state, is_(State.STOPPED))
        task.cont()
        task.join()
        assert_that(task.state, is_(State.FINISHED))

    @timelimit(1)
    def test_state_is_running_after_continue(self):
        task_ctrl = DummyTaskController()
        task = task_ctrl.create_task()
        task.start()
        try:
            task_ctrl.wait_until_started_or_fail()
            task.stop()
            task.cont()
            assert_that(task.state, is_(State.RUNNING))
        finally:
            task.terminate()

    def test_default_name_is_function_name(self):
        task = Task(noop)
        assert_that(task.name, is_(noop.__name__))

    def test_can_pass_name_at_construction(self):
        the_name = 'taskname'
        task = Task(noop, name=the_name)
        assert_that(task.name, is_(the_name))


class TestTaskpile(object):
    def setUp(self):
        self.taskpile = Taskpile()

    @staticmethod
    def _create_mocktask_in_state(state):

        task = MagicMock(spec=Task)
        task.state = state

        def start():
            task.state = State.RUNNING

        task.start.side_effect = start
        return task

    def test_can_add_task(self):
        task = Task(noop)
        self.taskpile.enqueue(task)
        assert_that(self.taskpile.pending, contains(task))

    def test_start_up_to_max_parallel_tasks_on(self):
        num_more = 2
        tasks = [self._create_mocktask_in_state(State.PENDING)
                 for i in xrange(self.taskpile.max_parallel + num_more)]
        for task in tasks:
            self.taskpile.enqueue(task)
        self.taskpile.update()
        for task in tasks[:-num_more]:
            task.start.assert_called_once_with()
        for task in tasks[-num_more:]:
            assert_that(task.start.called, is_(False))

    def test_starts_all_tasks_if_less_then_max(self):
        tasks = [self._create_mocktask_in_state(State.PENDING)
                 for i in max(1, xrange(self.taskpile.max_parallel - 1))]
        for task in tasks:
            self.taskpile.enqueue(task)
        self.taskpile.update()
        for task in tasks:
            task.start.assert_called_once_with()

    def test_starts_tasks_later_added_but_at_most_max_parallel(self):
        num_more = 2
        tasks = [self._create_mocktask_in_state(State.PENDING)
                 for i in xrange(self.taskpile.max_parallel + num_more)]
        self.taskpile.enqueue(tasks[0])
        self.taskpile.update()
        for task in tasks[1:]:
            self.taskpile.enqueue(task)
        self.taskpile.update()
        for task in tasks[:-num_more]:
            task.start.assert_called_once_with()
        for task in tasks[-num_more:]:
            assert_that(task.start.called, is_(False))

    def test_stop_newest_process_on_reducing_max_parallel(self):
        self.taskpile.max_parallel = 2
        tasks = [self._create_mocktask_in_state(State.PENDING)
                 for i in xrange(2)]
        for task in tasks:
            self.taskpile.enqueue(task)
        self.taskpile.update()
        self.taskpile.max_parallel = 1
        self.taskpile.update()
        tasks[1].stop.assert_called_once_with()
        assert_that(tasks[0].stop.called, is_(False))

    def test_continues_an_already_started_process(self):
        task = self._create_mocktask_in_state(State.STOPPED)
        self.taskpile.enqueue(task)
        self.taskpile.update()
        assert_that(task.start.called, is_(False))
        task.cont.assert_called_once_with()

    def test_update_sorts_queues(self):
        pending_tasks = [self._create_mocktask_in_state(State.PENDING)
                         for i in xrange(2)]
        running_tasks = [self._create_mocktask_in_state(State.RUNNING)
                         for i in xrange(2)]
        stopped_tasks = [self._create_mocktask_in_state(State.STOPPED)
                         for i in xrange(2)]
        finished_tasks = [self._create_mocktask_in_state(State.FINISHED)
                          for i in xrange(2)]
        self.taskpile.pending = [pending_tasks[0], running_tasks[0],
                                 stopped_tasks[0], finished_tasks[0]]
        self.taskpile.running = [pending_tasks[1], running_tasks[1],
                                 stopped_tasks[1], finished_tasks[1]]
        self.taskpile.max_parallel = len(running_tasks)
        self.taskpile.update()

        assert_that(
            self.taskpile.pending, contains(*stopped_tasks + pending_tasks))
        assert_that(self.taskpile.running, contains(*running_tasks))
        assert_that(self.taskpile.finished, contains(*finished_tasks))
