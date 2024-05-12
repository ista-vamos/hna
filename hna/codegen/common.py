import inspect
from os.path import basename


# This function dump the position from where it is called into the given file
def dump_codegen_position(f, end="\n"):
    parent_frame = inspect.getouterframes(inspect.currentframe())[1]
    msg = f"/* [CODEGEN]: {basename(parent_frame.filename)}:{parent_frame.function}:{parent_frame.lineno} */{end}"
    if callable(f):
        f(msg)
    else:
        f.write(msg)
