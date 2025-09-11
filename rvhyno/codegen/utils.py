import inspect
from os.path import basename


def dump_codegen_position(f, lvl=1, full_filename=False, end="\n"):
    """
    This function dump the position from where it is called into the given file

    It is a no-op in optimized code
    """
    if __debug__:
        parent_frame = inspect.getouterframes(inspect.currentframe())[lvl]
        if full_filename:
            filename = parent_frame.filename
        else:
            filename = basename(parent_frame.filename)
        msg = f"/* [CODEGEN]: {filename}:{parent_frame.function}:{parent_frame.lineno} */{end}"
        if callable(f):
            f(msg)
        else:
            f.write(msg)


def write_codegen_stack(f, lvl=1, full_filename=True, comment_str=r"//"):
    """
    This function dump the position from where it is called into the given file
    """
    wr = f if callable(f) else f.write
    wr(f"{comment_str} [CODEGEN] stack:\n")
    for n, frame in enumerate(
        reversed(inspect.getouterframes(inspect.currentframe())[lvl:])
    ):
        filename = frame.filename if full_filename else basename(frame.filename)
        # crop the path to this module
        try:
            filename = filename[filename.rindex("rvhyno") :]
        except ValueError:
            pass  # keep the whole name

        wr(f"{comment_str} [{n}] {filename}:{frame.function}:{frame.lineno}\n")
