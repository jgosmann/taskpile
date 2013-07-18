from hamcrest import assert_that, is_

from matcher import empty

from taskpile import Taskpile


class TestTaskpile(object):
    def test_job_queue_is_initially_empty(self):
        taskpile = Taskpile()
        assert_that(taskpile.queue, is_(empty()))
