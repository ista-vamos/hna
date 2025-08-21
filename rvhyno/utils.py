from sys import stdout, stderr

import inspect
from os.path import basename
from datetime import datetime


def code_position(f, end="\n"):
    """
    This function dump the position from where it is called into the given file

    It is a no-op in optimized code
    """
    if __debug__:
        parent_frame = inspect.getouterframes(inspect.currentframe())[1]
        return f"{basename(parent_frame.filename)}:{parent_frame.function}:{parent_frame.lineno}{end}"
    return ''


_logfile = None
_max_width = 0

def open_log(path):
    global _logfile
    _logfile = open(path, 'w')

    log(None, "RVHyno log", section=1)
    log('info', str(datetime.now()))
    return _logfile

def log(cls, *args, **kwargs):
    global _max_width
    if cls:
        _max_width = max(_max_width, len(cls))

    if _logfile:
        sec = kwargs.get("section")
        if sec:
            print("\n"+"#"*sec, *args, file=_logfile)
            print("", file=_logfile)
        else:
            if cls:
                print(f"[{cls.ljust(_max_width)}]", *args, file=_logfile)
            else:
                print(*args, file=_logfile)


def msg(cls, *args, **kwargs):
    global _max_width
    if cls is not None:
        _max_width = max(_max_width, len(cls))

    # write the message also to the logfile if it has been opened
    log(cls, *args, **kwargs)

    if kwargs.get('log_only'):
        return

    fl = kwargs.get("file", stderr if cls in ("dbg", "warn", "err") else stdout)
    cl = kwargs.get("color")
    if cl is None:
        if cls == "dbg":
            cl = "\033[0;37m"
        elif cls == "info":
            cl = "\033[0;36m"
        elif cls == "warn":
            cl = "\033[1;33m"
        elif cls == "err":
            cl = "\033[1;31m"

    section = kwargs.get("section") or 0
    if 0 < section < 3:
        print("------------------------------------------------------------", file=fl)
    if cl:
        print(cl, file=fl, end="")

    if section > 0:
        print("#" * section, file=fl, end=" ")

    if cls is not None:
        print(f"[{cls.ljust(_max_width)}]", *args, "\033[0m", file=fl)
    else:
        print(*args, "\033[0m", file=fl)

    if 0 < section < 3:
        print("------------------------------------------------------------", file=fl)

