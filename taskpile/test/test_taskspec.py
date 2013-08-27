from hamcrest import assert_that, contains
from taskpile.taskspec import TaskGroupSpec


class TestTaskGroupSpec(object):
    def test_replaces_spec_vars_in_cmd_spec(self):
        spec_str = '''
            somekey = somevalue

            [__spec__]
                cmd = somecmd --somekey %(somekey)r
            '''
        group = TaskGroupSpec.from_spec_str(spec_str)
        expected = {'somekey': 'somevalue', '__spec__': {
            'cmd': "somecmd --somekey 'somevalue'"}}
        assert_that(group.iter_specs(), contains(expected))
