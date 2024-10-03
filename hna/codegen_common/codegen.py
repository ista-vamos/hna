from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin

from vamos_common.codegen.codegen import CodeGen as CG


class CodeGen(CG):
    def __init__(
        self, name: str, args, ctx, out_dir: str = None, namespace: str = None
    ):
        super().__init__(args, ctx, out_dir)

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.common_templates_path = pathjoin(self_dir, "templates/cpp")
        self.templates_path = None  # must be set by child classes

        self._name = name
        self._namespace = namespace

        self._add_gen_files = []
        self._submonitors = []

    def name(self) -> str:
        return self._name

    def sub_name(self) -> str:
        return f"sub{self._name}"

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

    def submonitors(self):
        return self._submonitors
