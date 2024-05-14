from os import readlink, listdir, makedirs
from os.path import abspath, dirname, islink, join as pathjoin, basename
from subprocess import run

from hna.codegen.common import dump_codegen_position
from hna.codegen.hnl import CodeGenCpp as HNLCodeGenCpp
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
            "main.cpp",
            "hna-monitor.h",
            "hna-monitor.cpp",
            #
            "../monitor.h",
            "../trace.h",
            "../trace.cpp",
            "../traceset.h",
            "../traceset.cpp",
            "../cmd.h",
            "../cmd.cpp",
            "../verdict.h",
            "../csv.hpp",
        ]
        for f in files:
            if f not in self.args.overwrite_default:
                self.copy_file(f)

        for f in self.args.cpp_files:
            self.copy_file(f)

    def _generate_cmake(self, add_subdirs):
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
                "@ADD_SUBDIRS@": "".join(
                    f"add_subdirectory({subdir})\n" for subdir in add_subdirs
                ),
            },
        )

    def _generate_events(self, hna: HyperNodeAutomaton):

        with self.new_file("events.h") as f:
            wr = f.write
            wr("#ifndef EVENTS_H_\n#define EVENTS_H_\n\n")
            wr("#include <iostream>\n\n")
            # wr("#include <cassert>\n\n")

            wr("enum ActionEventType {\n")
            wr("  INVALID = 0,")
            wr("  EVENT,")
            for action in hna.actions():
                wr(f"  ACTION_{action},")
            wr("};\n")

            dump_codegen_position(wr)
            wr("struct Event {\n")
            for name, ty in self._event:
                wr(f"  {ty} {name};\n")
            wr("};\n\n")

            wr("std::ostream& operator<<(std::ostream& os, const Event& ev);\n")

            wr(
                """
            struct ActionEvent {
                ActionEventType type;
                Event event;
                
                bool isAction() const { return type > EVENT; }
            };\n
            """
            )

            wr("std::ostream& operator<<(std::ostream& os, const ActionEvent& ev);\n")

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

            wr("std::ostream& operator<<(std::ostream& os, const ActionEvent& ev) {\n")
            wr(' os << "ActionEvent(";\n\n')
            wr("switch(ev.type) {\n")
            for action in hna.actions():
                wr(f'case ACTION_{action}: os << "{action}"; break;\n')
            wr(f"case EVENT: os << ev; break;\n")
            wr(f"default: abort();\n")
            wr("}\n")
            wr('os << ")";\n\n')
            wr("return os;\n")
            wr("}\n")

    def _generate_csv_reader(self):
        self.copy_file("../csvreader.h")
        self.copy_file("../csvreader.cpp")
        self.args.add_gen_files.append("csvreader.cpp")

        with self.new_file("try_read_csv_event.cpp") as f:
            wr = f.write
            dump_codegen_position(wr)
            wr("auto it = row.begin();")
            for name, ty in self._event:
                wr(f"ev.{name} = it->get<{ty}>(); ++it;\n")

    def _gen_dispatch(self, hna, wr, call):
        wr("switch (type) {")
        for state in hna.states():
            state_id = hna.get_state_id(state)
            wr(
                f"case HNANodeType::NODE_{state_id}: static_cast<hnl_{state_id}::HNLMonitor*>(monitor.get())->{call}; break;"
            )
        wr(" default: abort();\n")
        wr("};\n")

    def _generate_monitor(self, hna):
        with self.new_file("hna_node_types.h") as f:
            wr = f.write
            dump_codegen_position(wr)

            wr("enum class HNANodeType {\n")
            for state in hna.states():
                state_id = hna.get_state_id(state)
                wr(f"NODE_{state_id} = {state_id},\n")
            wr("};\n")

        with self.new_file("hnl-monitors.h") as f:
            wr = f.write
            dump_codegen_position(wr)

            wr("#pragma once\n\n")
            for state in hna.states():
                state_id = hna.get_state_id(state)
                wr(f'#include "hnl-{state_id}/hnl-monitor.h"\n')

        with self.new_file("slices-tree-ctor.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            assert len(hna.initial_states()) == 1, hna.initial_states()

            init_id = hna.get_state_id(hna.initial_states()[0])
            wr(
                f"SlicesTree() : root(new hnl_{init_id}::HNLMonitor(), HNANodeType::NODE_{init_id}) {{}}\n\n"
            )

        with self.new_file("dispatch-new-trace.h") as f:
            dump_codegen_position(f)
            self._gen_dispatch(hna, f.write, "newTrace(trace_id)")
        with self.new_file("dispatch-trace-finished.h") as f:
            dump_codegen_position(f)
            self._gen_dispatch(hna, f.write, "traceFinished(trace_id)")
        with self.new_file("dispatch-extend-trace.h") as f:
            dump_codegen_position(f)
            self._gen_dispatch(hna, f.write, "extendTrace(trace_id, ev)")

    def generate(self, hna: HyperNodeAutomaton):
        """
        The top-level function to generate code
        """

        self._generate_events(hna)

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

        ctx = None
        cmake_subdirs = []
        for state in hna.states():
            hnl_id = hna.get_state_id(state)
            subdir = f"hnl-{hnl_id}"
            cmake_subdirs.append(subdir)

            embedding_data = {
                "monitor_name": f"monitor_{hnl_id}",
                "tests": True,
            }
            hnl_codegen = HNLCodeGenCpp(
                self.args, ctx, f"{self.out_dir}/{subdir}", namespace=f"hnl_{hnl_id}"
            )
            hnl_codegen.generate_embedded(state.formula, alphabet, embedding_data)

        self._generate_monitor(hna)

        self._copy_common_files()
        # cmake generation should go at the end so that
        # it knows all the generated files
        self._generate_cmake(cmake_subdirs)

        # format the files if we have clang-format
        # FIXME: check clang-format properly instead of catching the exception
        try:
            for path in listdir(self.out_dir):
                if path.endswith(".h") or path.endswith(".cpp"):
                    run(["clang-format", "-i", f"{self.out_dir}/{path}"])
        except FileNotFoundError:
            pass
