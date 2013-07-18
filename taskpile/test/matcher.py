from hamcrest.core.base_matcher import BaseMatcher


class Empty(BaseMatcher):
    def _matches(self, item):
        if hasattr(item, '__len__'):
            return len(item) == 0
        elif hasattr(item, 'count'):
            return item.count() == 0
        raise TypeError('%s cannot be tested for emptiness.' % (
            type(item).__name__))

    def describe_to(self, description):
        description.append_text('empty')


def empty():
    return Empty()
