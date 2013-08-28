import itertools
import string
from StringIO import StringIO

from configobj import ConfigObj

from sanitize import quote_for_shell


class TaskSpecCmdFormatter(string.Formatter):
    def parse(self, format_string):
        for literal_text, field_name, format_spec, conversion in super(
                TaskSpecCmdFormatter, self).parse(format_string):
            if conversion == 't':
                if format_spec != '':
                    format_spec = ':' + format_spec
                literal_text = '{}{{{}!{}{}}}'.format(
                    literal_text, field_name, conversion, format_spec)
                field_name = format_spec = conversion = None
            yield literal_text, field_name, format_spec, conversion

    def convert_field(self, value, conversion):
        if conversion == 'q':
            return quote_for_shell(value)
        else:
            return super(TaskSpecCmdFormatter, self).convert_field(
                value, conversion)


class TaskGroupSpec(object):
    CMD_KEY = '__cmd__'
    NAME_KEY = '__name__'

    __cmd_formatter = TaskSpecCmdFormatter()

    def __init__(self, group_spec):
        self.group_spec = group_spec

    @classmethod
    def from_spec_str(cls, spec_str):
        return cls(ConfigObj(StringIO(spec_str), interpolation=False))

    @classmethod
    def from_spec_file(cls, filename):
        return cls(ConfigObj(filename, interpolation=False))

    def iter_specs(self):
        for spec in self._iter_subspecs(self.group_spec):
            spec[self.CMD_KEY] = self.__cmd_formatter.format(
                spec[self.CMD_KEY], **spec)
            yield spec

    def _iter_subspecs(self, spec):
        value_lists, spec_gens = self._split_into_value_lists_and_spec_gens(
            spec)

        for value_set in itertools.product(*value_lists.values()):
            base = {self.NAME_KEY: ''}
            for key, value in zip(value_lists.keys(), value_set):
                base[key] = value

                if len(value_lists[key]) > 1:
                    if len(base[self.NAME_KEY]) > 0:
                        base[self.NAME_KEY] += ' '
                    base[self.NAME_KEY] += '{0}={1}'.format(key, value)

            for merged in self._iter_merged_with_spec_gens(base, spec_gens):
                yield merged

    def _split_into_value_lists_and_spec_gens(self, spec):
        value_lists = {}
        spec_gens = []
        for k, v in spec.items():
            if hasattr(v, 'items'):
                spec_gens.append((k, v))
            elif len(k) > 1 and k[0] == '_' and k[1] != '_':
                value_lists[k[1:]] = v
            else:
                value_lists[k] = [v]
        return value_lists, spec_gens

    def _iter_merged_with_spec_gens(self, base, spec_gens):
        if len(spec_gens) <= 0:
            yield base
        else:
            for name, gen in spec_gens:
                for spec in self._iter_subspecs(gen):
                    merged = base.copy()
                    merged.update(spec)
                    merged[self.NAME_KEY] = '{0} {1}: {2}'.format(
                        base[self.NAME_KEY], name, merged[self.NAME_KEY])
                    yield merged
