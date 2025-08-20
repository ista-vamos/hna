from os import mkdir, listdir
from os import readlink
from os.path import islink
from os.path import join as pathjoin, abspath, dirname
from shutil import rmtree, copy as shutilcopy
from subprocess import run
from sys import stderr, stdout

from jinja2 import Environment, FileSystemLoader

def msg(cls, *args, **kwargs):
    fl = kwargs.get("file", stdout)
    cl = kwargs.get("color")
    if cl is None:
        if cls == "info":
            cl = "\033[0;36m"
        elif cls == "warn":
            cl = "\033[1;33m"
    if cl:
        print(cl, file=fl, end="")
    print(f"[{cls.upper()}]", *args, "\033[0m", file=fl)


class CodeGen:
    def __init__(
        self,
        name: str,
        args,
        out_dir: str = None,
        namespace: str = None,
        embedded=False,
    ):
        self._out_dir = abspath(out_dir or args.out_dir)

        self.args = args
        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.common_templates_path = pathjoin(self_dir, "templates/cpp")
        self.templates_path = None  # must be set by child classes

        self._name = name
        self._namespace = namespace
        # is this code a subdirectory of a top-level cmake-based project?
        self._embedded = embedded

        self._generated_files = []
        self._add_gen_files = []
        self._submonitors = []

        out_dir_overwrite = args.out_dir_overwrite
        msg(
            "info",
            f"output dir: {out_dir} {'(overwriting not allowed)' if not out_dir_overwrite else ''}",
            file=stderr,
        )

        self.create_out_dir(out_dir_overwrite)

        if args.debug:
            try:
                mkdir(f"{self.out_dir}/dbg")
            except OSError:
                pass  # exists

    def create_out_dir(self, overwrite_if_exists: bool = False):
        try:
            mkdir(self._out_dir)
        except OSError:
            if overwrite_if_exists:
                msg(
                    "warn",
                    "the output dir exists, overwriting its contents",
                    file=stderr,
                )
                rmtree(self._out_dir)
                mkdir(self._out_dir)

    def copy_file(self, name: str, to: str = None, from_dir: str = None):
        """
        Copy the file `name` into `out_dir`. If `name` is not an absolute path,
        it is looked for in `from_dir` if given, otherwise in `self.templates_path`.
        If `to` is given, the file is copied into `out_dir/to`.
        (All the directories subsumed by `to` must exist)
        ```
        in = name is relative ? (from_dir ? from_dir : templates_path/name) : name
        out = to ? out_dir/to : out_dir
        cp in out
        ```
        """
        if name[0] == "/":
            path = name
        else:
            path = pathjoin(from_dir if from_dir else self.templates_path, name)

        if to:
            shutilcopy(path, f"{self._out_dir}/{to}")
        else:
            shutilcopy(path, self._out_dir)

    def new_file(self, name: str):
        if name in self.args.overwrite_file:
            filename = "/dev/null"
        else:
            filename = pathjoin(self._out_dir, name)
            assert filename not in self._generated_files, (
                filename,
                self._generated_files,
            )
            self._generated_files.append(filename)
        return open(filename, "w")

    def get_output_path(self, name: str) -> str:
        return pathjoin(self._out_dir, name)

    def new_dbg_file(self, name: str):
        filename = pathjoin(self._out_dir, "dbg/", name)
        return open(filename, "w")

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

    def gen_file(self, template, outfile, values):
        """
        Generate a file from a template `template` and writing the resulting
        file into `outfile`.
        """
        if outfile in self.args.overwrite_file:
            return

        outfile = self.get_output_path(outfile)
        msg('dbg', f'gen `{template}` -> `{outfile}`')

        tenv = Environment(loader=FileSystemLoader(self.templates_path))
        template = tenv.get_template(template)

        with open(outfile, 'w') as ofl:
            ofl.write(template.render(**values))


    def get_template_path(self, template: str) -> str:
        return pathjoin(self.templates_path, template)

    gen_config = gen_file

    def input_file(self, stream, name: str):
        """
        Write the contents of the file `name` into the stream `stream`.

        :param stream:  stream to write to
        :param name:  name of the file (residing in `self.templates_path`) to write into `stream`
        """
        inpath = self.get_template_path(name)
        with open(inpath, "r") as infl:
            write = stream.write
            for line in infl:
                write(line)

    def try_clang_format_file(self, name):
        from subprocess import run

        run(["clang-format", "-i", self.get_output_path(name)])

    def format_generated_code(self, dir_path=None):
        # format the files if we have clang-format
        # FIXME: check clang-format properly instead of catching the exception
        try:
            for path in listdir(dir_path or self._out_dir):
                if path.endswith(".h") or path.endswith(".cpp"):
                    run(["clang-format", "-i", f"{self._out_dir}/{path}"])
        except FileNotFoundError:
            pass
