import itertools
from StringIO import StringIO

from configobj import ConfigObj


class TaskGroupSpec(object):
    CMD_KEY = '__cmd__'

    def __init__(self, group_spec):
        self.group_spec = group_spec

    @classmethod
    def from_spec_str(cls, spec_str):
        return cls(ConfigObj(StringIO(spec_str), interpolation=False))

    def iter_specs(self):
        for spec in self._iter_subspecs(self.group_spec):
            spec[self.CMD_KEY] %= spec
            yield spec

    def _iter_subspecs(self, spec):
        value_lists = {}
        spec_gens = []
        for k, v in spec.items():
            if hasattr(v, 'items'):
                spec_gens.append(v)
            elif len(k) > 1 and k[0] == '_' and k[1] != '_':
                value_lists[k[1:]] = v
            else:
                value_lists[k] = [v]
        if len(spec_gens) <= 0:
            for value_set in itertools.product(*value_lists.values()):
                merged = {}
                for key, value in zip(value_lists.keys(), value_set):
                    merged[key] = value
                yield merged
        else:
            for gen in spec_gens:
                for spec in self._iter_subspecs(gen):
                    for value_set in itertools.product(*value_lists.values()):
                        merged = {}
                        for key, value in zip(value_lists.keys(), value_set):
                            merged[key] = value
                        merged.update(spec)
                        yield merged
