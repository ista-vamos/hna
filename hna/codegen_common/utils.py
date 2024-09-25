import inspect
from os.path import basename
from sys import stderr


def dump_codegen_position(f, end="\n"):
    """
    This function dump the position from where it is called into the given file

    It is a no-op in optimized code
    """
    if __debug__:
        parent_frame = inspect.getouterframes(inspect.currentframe())[1]
        msg = f"/* [CODEGEN]: {basename(parent_frame.filename)}:{parent_frame.function}:{parent_frame.lineno} */{end}"
        if callable(f):
            f(msg)
        else:
            f.write(msg)


def FIXME(f, msg, only_comment=False, to_stderr=True):
    dump_codegen_position(f)
    if only_comment:
        msg = f"/* FIXME: {msg} */\n"
    else:
        msg = f'std::cerr << "FIXME: {msg} \\n";'
    if to_stderr:
        print(f"/* FIXME: {msg} */", file=stderr)
    if callable(f):
        f(msg)
    else:
        f.write(msg)
