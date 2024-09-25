from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin

from vamos_common.codegen.codegen import CodeGen as CG


class CodeGen(CG):
    def __init__(self, args, ctx, out_dir: str = None):
        super().__init__(args, ctx, out_dir)

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.common_templates_path = pathjoin(self_dir, "templates/cpp")
        self.templates_path = None  # must be set by child classes

        self._add_gen_files = []
