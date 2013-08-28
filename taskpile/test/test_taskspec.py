from hamcrest import all_of, assert_that, contains, contains_inanyorder, \
    contains_string, has_entries
from taskpile.taskspec import TaskGroupSpec


class TestTaskGroupSpec(object):
    def test_replaces_spec_vars_in_cmd_spec(self):
        spec_str = '''
            somekey = somevalue
            __cmd__ = somecmd --somekey {somekey!r}
            '''
        group = TaskGroupSpec.from_spec_str(spec_str)
        expected = {
            'somekey': 'somevalue',
            '__cmd__': "somecmd --somekey 'somevalue'"}
        assert_that(group.iter_specs(), contains(has_entries(expected)))

    def test_can_use_sections_to_instantiate_task_specs(self):
        spec_str = '''
            __cmd__ = {task_id} {sub}
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
        assert_that(group.iter_specs(), contains_inanyorder(
            *[has_entries(entries) for entries in expected]))

    def test_can_use_parameter_lists_to_instatiate_task_specs(self):
        spec_str = '''
            __cmd__ = {value0} {value1}
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
        assert_that(group.iter_specs(), contains_inanyorder(
            *[has_entries(entries) for entries in expected]))

    def test_generates_a_descriptive_name(self):
        spec_str = '''
            __cmd__ = cmd
            _value0 = 1, 2
            [multitask]
                _value1 = 3, 4
            [another_task]
                value1 = 5
            '''
        group = TaskGroupSpec.from_spec_str(spec_str)
        expected_names = [
            all_of(
                contains_string('value0=1'),
                contains_string('value1=3'),
                contains_string('multitask')),
            all_of(
                contains_string('value0=1'),
                contains_string('value1=4'),
                contains_string('multitask')),
            all_of(
                contains_string('value0=1'),
                contains_string('another_task')),
            all_of(
                contains_string('value0=2'),
                contains_string('value1=3'),
                contains_string('multitask')),
            all_of(
                contains_string('value0=2'),
                contains_string('value1=4'),
                contains_string('multitask')),
            all_of(
                contains_string('value0=2'),
                contains_string('another_task'))]
        assert_that(
            [s['__name__'] for s in group.iter_specs()],
            contains_inanyorder(*expected_names))

    def test_leaves_template_file_replacements_unchanged(self):
        spec_str = '''
            __cmd__ = cmd {config_template!t}
            config_template = ./somefile
            '''
        group = TaskGroupSpec.from_spec_str(spec_str)
        expected = {
            'config_template': './somefile',
            '__cmd__': "cmd {config_template!t}"}
        assert_that(group.iter_specs(), contains(has_entries(expected)))
