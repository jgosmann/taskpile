from multiprocessing import util
import os


# See <http://bugs.python.org/issue14548>. That issue is fixed in recent
# versions of Python 3, but not in Python 2.7.
UnpatchedFinalize = util.Finalize


class PatchedFinalize(UnpatchedFinalize):
    def __init__(self, *args, **kwargs):
        UnpatchedFinalize.__init__(self, *args, **kwargs)
        self._pid = os.getpid()

    def __call__(self, *args, **kwargs):
        '''
        Run the callback unless it has already been called or cancelled
        '''
        if self._pid != os.getpid():
            util.sub_debug('finalizer ignored because different process')
            self._weakref = self._callback = self._args = \
                self._kwargs = self._key = None
            return None
        else:
            return UnpatchedFinalize.__call__(self, *args, **kwargs)

util.Finalize = PatchedFinalize
