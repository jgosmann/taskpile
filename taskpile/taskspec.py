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
        base_spec = {}
        spec_gens = []
        for k, v in spec.items():
            if hasattr(v, 'items'):
                spec_gens.append(v)
            else:
                base_spec[k] = v
        if len(spec_gens) <= 0:
            yield base_spec
        else:
            for gen in spec_gens:
                for spec in self._iter_subspecs(gen):
                    merged = base_spec.copy()
                    merged.update(spec)
                    yield merged
