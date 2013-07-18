from multiprocessing import Pipe

from hamcrest import assert_that, contains, has_property, is_

from matcher import empty

from taskpile import Taskpile


class DummyTask(object):
    def __init__(self):
        self.__parent_pipe, self.__child_pipe = Pipe()

    def __call__(self):
        self.__child_pipe.recv()
        self.__child_pipe.close()

    def finish(self):
        self.__parent_pipe.send('arbitrary data to cause exit')
        self.__parent_pipe.close()


class TestTaskpile(object):
    def setUp(self):
        self.taskpile = Taskpile()

    def test_task_queue_is_initially_empty(self):
        assert_that(self.taskpile.queue, is_(empty()))

    def test_can_add_task_which_will_run_immediatly(self):
        self.taskpile.enqueue(DummyTask())
        assert_that(
            self.taskpile.queue, contains(has_property('state', 'RUNNING')))
