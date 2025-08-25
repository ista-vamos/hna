from os import mkdir, listdir
from os import readlink
from os.path import islink
from os.path import join as pathjoin, abspath, dirname
from shutil import rmtree, copy as shutilcopy
from subprocess import run
from sys import stderr

from jinja2 import Environment, FileSystemLoader

from rvhyno.utils import msg, log


class CodeGen:
    """
    The super-class for code generation. Particular code generation classes will inherit from this.
    At this moment, there is only the `CodeGenCpp` and its sub-classes.
    `CodeGenCpp` is used to generate C++ code for the monitors.
    """
    def __init__(
        self,
        name: str,
        args,
        out_dir: str = None,
        embedded=False,
    ):
        self._out_dir = abspath(out_dir or args.out_dir)

        self.args = args
        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        # these are templates that are common to the whole generated project
        self.common_templates_path = pathjoin(self_dir, "templates/cpp")
        # these are templates specific to the currently generated monitor
        # This attribute is set by sub-classes
        self.templates_path = None

        # name of the monitor that this `CodeGen` generates
        self._name = name
        # is this code a subdirectory of a top-level cmake-based project?
        self._embedded = embedded

        self._generated_files = []
        self._add_gen_files = []
        self._submonitors = []

        out_dir_overwrite = args.out_dir_overwrite
        msg(
            "info",
            f"output dir: {self._out_dir} {'(overwriting not allowed)' if not out_dir_overwrite else ''}",
            file=stderr,
        )

        self.create_out_dir(out_dir_overwrite)

        if args.debug:
            try:
                mkdir(f"{self._out_dir}/dbg")
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

    def submonitors(self):
        return self._submonitors

    def gen_file(self, template, outfile, values, creation_header="c++"):
        """
        Generate a file from a template `template` and writing the resulting
        file into `outfile`.
        """
        if outfile in self.args.overwrite_file:
            return

        outfile = self.get_output_path(outfile)
        log('dbg', f'gen `{template}` -> `{outfile}`')

        tenv = Environment(loader=FileSystemLoader(self.templates_path))
        template = tenv.get_template(template)

        with open(outfile, 'w') as ofl:
            if creation_header == "c++" and\
                (template.filename.endswith("cpp.in")  or template.filename.endswith("h.in")):
                ofl.write(f"// Generated from `{template.filename}`\n\n")
            ofl.write(template.render(**values))


    def get_template_path(self, template: str) -> str:
        return pathjoin(self.templates_path, template)

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


    def format_generated_code(self, dir_path=None):
        # format the files if we have clang-format
        # FIXME: check clang-format properly instead of catching the exception
        try:
            for path in listdir(dir_path or self._out_dir):
                if path.endswith(".h") or path.endswith(".cpp"):
                    run(["clang-format", "-i", f"{self.get_output_path(path)}"])
        except FileNotFoundError:
            pass
