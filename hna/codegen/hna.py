from os import readlink, listdir, makedirs
from os.path import abspath, dirname, islink, join as pathjoin, basename
from subprocess import run

from hna.codegen.common import dump_codegen_position
from hna.hna.automaton import HyperNodeAutomaton
from hna.hnl.formula import Constant
from hna.hnl.parser import Parser as HNLParser
from vamos_common.codegen.codegen import CodeGen


class CodeGenCpp(CodeGen):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.
    """

    def __init__(self, args, ctx):
        super().__init__(args, ctx)

        self_path = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_path, "templates/cpp/hna")

        assert (
            self.args.csv_header
        ), "Give --csv-header, other methods not supported yet"
        self._event = [
            [s.strip() for s in event.split(":")]
            for event in self.args.csv_header.split(",")
        ]

        makedirs(f"{self.out_dir}/tests", exist_ok=True)

    def _copy_common_files(self):
        files = [
            "../trace.h",
            "../trace.cpp",
            "../traceset.h",
            "main.cpp",
            "../cmd.h",
            "../cmd.cpp",
            # "monitor.h",
            # "monitor.cpp",
            "../verdict.h",
            "../csv.hpp",
        ]
        for f in files:
            if f not in self.args.overwrite_default:
                self.copy_file(f)

        for f in self.args.cpp_files:
            self.copy_file(f)

    def _generate_cmake(self):
        from config import vamos_buffers_DIR

        build_type = self.args.build_type
        if not build_type:
            build_type = '"Debug"' if self.args.debug else ""

        self.gen_config(
            "CMakeLists.txt.in",
            "CMakeLists.txt",
            {
                "@vamos-buffers_DIR@": vamos_buffers_DIR,
                "@additional_sources@": " ".join(
                    (basename(f) for f in self.args.cpp_files + self.args.add_gen_files)
                ),
                "@additional_cflags@": " ".join((d for d in self.args.cflags)),
                "@CMAKE_BUILD_TYPE@": build_type,
            },
        )

    def _generate_events(self):
        with self.new_file("events.h") as f:
            wr = f.write
            wr("#ifndef EVENTS_H_\n#define EVENTS_H_\n\n")
            wr("#include <iostream>\n\n")
            # wr("#include <cassert>\n\n")

            dump_codegen_position(wr)
            wr("struct Event {\n")
            for name, ty in self._event:
                wr(f"  {ty} {name};\n")
            wr("};\n\n")

            wr("std::ostream& operator<<(std::ostream& os, const Event& ev);\n")

            wr("#endif\n")

        with self.new_file("events.cpp") as f:
            wr = f.write
            wr("#include <iostream>\n\n")
            wr('#include "events.h"\n\n')
            dump_codegen_position(wr)
            wr("std::ostream& operator<<(std::ostream& os, const Event& ev) {\n")
            wr('  os << "("')
            for n, field in enumerate(self._event):
                name, ty = field
                if n > 0:
                    wr(f'  << ", "')
                wr(f'  << "{name} = " << ev.{name}')
            wr('   << ")";\n')
            wr("return os;\n")
            wr("}\n")

    def _generate_csv_reader(self):
        self.copy_file("csvreader.h")
        self.copy_file("csvreader.cpp")
        self.args.add_gen_files.append("csvreader.cpp")

        with self.new_file("try_read_csv_event.cpp") as f:
            wr = f.write
            dump_codegen_position(wr)
            wr("auto it = row.begin();")
            for name, ty in self._event:
                wr(f"ev.{name} = it->get<{ty}>(); ++it;\n")

    def _generate_monitor(self, formula):
        pass

    def generate(self, hna: HyperNodeAutomaton):
        """
        The top-level function to generate code
        """

        self._generate_events()

        if self.args.gen_csv_reader:
            self._generate_csv_reader()

        parser = HNLParser()
        for s in hna.states():
            s.formula = parser.parse_text(s.formula)
            print(s.formula)

        if not self.args.alphabet:
            alphabet = list(
                set((c for state in hna.states() for c in state.formula.constants()))
            )
            print("No alphabet given, using constants from the formulas: ", alphabet)
        else:
            alphabet = [Constant(a) for a in self.args.alphabet]

        assert alphabet, "The alphabet is empty"

        self._generate_monitor(hna)

        self._copy_common_files()
        # cmake generation should go at the end so that
        # it knows all the generated files
        self._generate_cmake()

        # format the files if we have clang-format
        # FIXME: check clang-format properly instead of catching the exception
        try:
            for path in listdir(self.out_dir):
                if path.endswith(".h") or path.endswith(".cpp"):
                    run(["clang-format", "-i", f"{self.out_dir}/{path}"])
        except FileNotFoundError:
            pass
