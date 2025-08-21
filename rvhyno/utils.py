from sys import stdout, stderr

from rvhyno.codegen.utils import dump_codegen_position


_max_width = 0
def msg(cls, *args, **kwargs):
    global _max_width
    _max_width = max(_max_width, len(cls))

    fl = kwargs.get("file", stdout)
    cl = kwargs.get("color")
    if cl is None:
        if cls == "info":
            cl = "\033[0;36m"
        elif cls == "warn":
            cl = "\033[1;33m"
    if cl:
        print(cl, file=fl, end="")
    print(f"[{cls.upper().ljust(_max_width)}]", *args, "\033[0m", file=fl)
