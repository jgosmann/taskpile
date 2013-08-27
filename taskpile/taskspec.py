from StringIO import StringIO

from configobj import ConfigObj


class TaskGroupSpec(object):
    SPEC_KEY = '__spec__'
    CMD_KEY = 'cmd'

    def __init__(self, group_spec):
        self.group_spec = group_spec

    @classmethod
    def from_spec_str(cls, spec_str):
        return cls(ConfigObj(StringIO(spec_str)))

    def iter_specs(self):
        task_spec = self.group_spec.copy()
        task_spec[self.SPEC_KEY][self.CMD_KEY] %= self.group_spec
        yield task_spec
