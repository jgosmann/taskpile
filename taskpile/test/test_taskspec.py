from hamcrest import assert_that, contains, contains_inanyorder
from taskpile.taskspec import TaskGroupSpec


class TestTaskGroupSpec(object):
    def test_replaces_spec_vars_in_cmd_spec(self):
        spec_str = '''
            somekey = somevalue
            __cmd__ = somecmd --somekey %(somekey)r
            '''
        group = TaskGroupSpec.from_spec_str(spec_str)
        expected = {
            'somekey': 'somevalue',
            '__cmd__': "somecmd --somekey 'somevalue'"}
        assert_that(group.iter_specs(), contains(expected))

    def test_can_use_sections_to_instantiate_task_specs(self):
        spec_str = '''
            __cmd__ = %(task_id)s %(sub)s
            same4all = same

            [task 0]
                task_id = 0
                [[subtask0-0]]
                    sub = 0
                [[subtaskX-1]]
                    task_id = X
                    sub = 1

            [task 1]
                task_id = 1
                sub = X
            '''
        group = TaskGroupSpec.from_spec_str(spec_str)
        expected = [
            {'same4all': 'same', 'task_id': '0', 'sub': '0', '__cmd__': '0 0'},
            {'same4all': 'same', 'task_id': 'X', 'sub': '1', '__cmd__': 'X 1'},
            {'same4all': 'same', 'task_id': '1', 'sub': 'X', '__cmd__': '1 X'}
        ]
        assert_that(group.iter_specs(), contains_inanyorder(*expected))

    def test_can_use_parameter_lists_to_instatiate_task_specs(self):
        spec_str = '''
            __cmd__ = %(value0)s %(value1)s
            _value0 = 1, 2, '1, 2'
            _value1 = 1, 2
            '''
        group = TaskGroupSpec.from_spec_str(spec_str)
        expected = [
            {'value0': '1', 'value1': '1', '__cmd__': '1 1'},
            {'value0': '2', 'value1': '1', '__cmd__': '2 1'},
            {'value0': '1, 2', 'value1': '1', '__cmd__': '1, 2 1'},
            {'value0': '1', 'value1': '2', '__cmd__': '1 2'},
            {'value0': '2', 'value1': '2', '__cmd__': '2 2'},
            {'value0': '1, 2', 'value1': '2', '__cmd__': '1, 2 2'}
        ]
        assert_that(list(group.iter_specs()), contains_inanyorder(*expected))
