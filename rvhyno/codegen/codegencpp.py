from rvhyno.codegen.codegen import CodeGen


class CodeGenCpp(CodeGen):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.

    This particular class takes care of creating `main.cpp` and files
    shared with all the (sub-)monitors.
    For actual monitors, there are other codegens (used by this class).
    """

    def __init__(
        self,
        args,
        out_dir: str = None,
        namespace: str = None,
        name="monitor",
        embedded=False,
    ):
        super().__init__(name=name, args=args, out_dir=out_dir, embedded=embedded)
        self._namespace = namespace

    def sub_namespace(self) -> str:
        return f"{self._namespace}::sub" if self._namespace else "sub"

    def namespace(self) -> str:
        return self._namespace or ""

    def namespace_start(self) -> str:
        return "\n".join(
            (
                f"namespace {ns} {{"
                for ns in (self._namespace.split("::") if self._namespace else ())
            )
        )

    def namespace_end(self) -> str:
        return "\n".join(
            (
                f"}} /* namespace {ns} */"
                for ns in (self._namespace.split("::")[::-1] if self._namespace else ())
            )
        )
