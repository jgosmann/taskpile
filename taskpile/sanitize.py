try:
    from shlex import quote as quote_for_shell
except ImportError:
    import re

    # Code copied from Python 3.3 implementation
    # <http://hg.python.org/cpython/file/2a59428dbff5/Lib/shlex.py>
    # It is licensed under the PSF License Agreement for Python 3.3.2. See
    # <http://docs.python.org/3.3/license.html#terms-and-conditions-for-accessing-or-otherwise-using-python>
    _find_unsafe = re.compile(r'[^\w@%+=:,./-]').search

    def quote_for_shell(s):
        """Return a shell-escaped version of the string *s*."""
        if not s:
            return "''"
        if _find_unsafe(s) is None:
            return s

        # use single quotes, and put single quotes into double quotes
        # the string $'b is then quoted as '$'"'"'b'
        return "'" + s.replace("'", "'\"'\"'") + "'"
