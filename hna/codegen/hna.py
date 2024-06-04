from os import readlink, listdir, makedirs
from os.path import abspath, dirname, islink, join as pathjoin, basename
from subprocess import run

from hna.codegen.common import dump_codegen_position, FIXME
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
        self._add_gen_files = []

        assert (
            self.args.csv_header
        ), "Give --csv-header, other methods not supported yet"
        self._event = [
            [s.strip() for s in event.split(":")]
            for event in self.args.csv_header.split(",")
        ]

        makedirs(f"{self.out_dir}/tests", exist_ok=True)

    def FIXME(self, f, msg):
        if self.args.debug:
            FIXME(f, msg)
        else:
            FIXME(f, msg, only_comment=True)

    def _copy_common_files(self):
        files = [
            "main.cpp",
            "hna-monitor.h",
            "hna-monitor.cpp",
            #
            "../monitor.h",
            "../atom-base.h",
            "../atom-evaluation-state.h",
            "../hnl-monitor-base.h",
            "../function.h",
            "../stream.h",
            "../trace.h",
            "../trace.cpp",
            "../traceset.h",
            "../traceset.cpp",
            "../tracesetview.h",
            "../tracesetview.cpp",
            "../sharedtraceset.h",
            "../sharedtraceset.cpp",
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

    def _generate_cmake(self, add_subdirs, monitor_names):
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
                    (
                        basename(f)
                        for f in self.args.cpp_files
                        + self.args.add_gen_files
                        + self._add_gen_files
                    )
                ),
                "@additional_cflags@": " ".join((d for d in self.args.cflags)),
                "@CMAKE_BUILD_TYPE@": build_type,
                "@ADD_SUBDIRS@": "".join(
                    f"add_subdirectory({subdir})\n" for subdir in add_subdirs
                ),
                "@LINK_HNL_MONITORS@": "".join(
                    f"target_link_libraries(monitor PUBLIC hnl{monitor_name} atoms{monitor_name})\n"
                    for monitor_name in monitor_names
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
            wr(f"case EVENT: os << ev.event; break;\n")
            wr(f"default: abort();\n")
            wr("}\n")
            wr('os << ")";\n\n')
            wr("return os;\n")
            wr("}\n")

    def _generate_csv_reader(self, hna):
        self.copy_file("../csvreader.h")
        self.copy_file("../csvreader.cpp")
        self._add_gen_files.append("csvreader.cpp")

        # def first(strings):
        #    return [s[0] for s in strings]
        # def deriv(strings, letter):
        #    return [s[1:] for s in strings if strings[0] == letter]

        with self.new_file("csvreader-aux.h") as f:
            wr = f.write
            dump_codegen_position(f)
            wr("#pragma once\n\n")
            wr('#include "events.h"\n\n')
            wr(
                "template <typename StreamTy> ActionEventType getAction(StreamTy &stream) {"
            )
            self.FIXME(wr, "Match the actions using DWAG")
            # state = hna.actions()
            # assert state, "No actions given"
            # wr('int ch;')
            # while state:
            #    wr('if ((ch = stream.get()) == EOF) { return INVALID; }\n')
            #    for letter in first(state):
            #        wr(f" if(ch == '{letter}') {{\n")
            #        wr('}\n')

            wr(
                """
            std::string tmp;
            stream >> std::ws;
            stream >> tmp;
            if (stream.fail()) {
              std::cerr << "Failed trying to read action\\n";
              abort();
            }
            stream >> std::ws;
            """
            )
            for action in hna.actions():
                wr(f'if (tmp == "{action}") {{ return ACTION_{action}; }}\n')

            wr(" return INVALID;")
            wr("}\n")

        with self.new_file("read_csv_event.h") as f:
            wr = f.write
            wr(f"ev.type = EVENT;\n")
            wr(f"int ch;\n\n")
            for n, tmp in enumerate(self._event):
                name, ty = tmp
                # wr(f"char action[{max_len_action_name}];\n\n")
                wr(f"_stream >> ev.event.{name};\n")
                wr("if (_stream.fail()) {")
                if n == 0:  # assume this is the header
                    wr(" if (_events_num_read == 0) {\n")
                    wr("   _stream.clear(); // assume this is the header\n")
                    self.FIXME(wr, "check that the header matches the events")
                    wr("   // ignore the rest of the line and try with the next one\n")
                    wr(
                        "   _stream.ignore(std::numeric_limits<std::streamsize>::max(), '\\n');\n"
                    )
                    wr(f"   _stream >> ev.event.{name};\n")
                    wr("    if (_stream.fail()) {")
                    wr(
                        f'    std::cerr << "Failed reading column \'{name}\' on line " << _events_num_read + 1 << "\\n";'
                    )
                    wr("    abort();")
                    wr("  }")
                    wr("} else {")
                    wr(
                        """
                        _stream.clear();
                        ev.type = getAction(_stream);
                        if (ev.isAction()) {
                          //std::cout << "[" << id() << "] IN: " << ev << "\\n";
                          return true;
                        } else {
                        """
                        f'   std::cerr << "Failed reading column \'{name}\' on line " << _events_num_read + 1 << "\\n";'
                        "}\n"
                    )
                    wr("    abort();")
                    wr("}")
                else:
                    wr(
                        f'  std::cerr << "Failed reading column \'{name}\' on line " << _events_num_read + 1 << "\\n";'
                    )
                    wr("  abort();")
                wr("}")
                if n == len(self._event) - 1:
                    wr(
                        f"""
                    while ((ch = _stream.get()) != EOF) {{
                      if (ch == '\\n') {{
                        break;
                      }}

                      if (!std::isspace(ch)) {{
                        std::cerr << "Wrong input on line " << _events_num_read + 1 << " after reading column '{name}'\\n";
                        std::cerr << "Expected the end of line, got '" << static_cast<char>(ch) << "'\\n";
                        abort();
                      }}
                    }}
                    """
                    )
                else:
                    wr(
                        f"""
                    while ((ch = _stream.get()) != EOF) {{
                      if (ch == ',') {{
                        break;
                      }}

                      if (!std::isspace(ch) || ch == '\\n') {{
                        std::cerr << "Wrong input on line " << _events_num_read + 1 << " after reading column '{name}'\\n";
                        std::cerr << "Expected next column (',' character), got '" << static_cast<char>(ch) << "'\\n";
                        abort();
                      }}
                    }}
                    """
                    )

    def _gen_create_hnl_monitor(self, hna):
        with self.new_file("create-hnl-monitor.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            wr("HNLMonitorBase *createHNLMonitor(HNANodeType node) {")
            wr(" switch (node) {")
            for state in hna.states():
                state_id = hna.get_state_id(state)
                wr(
                    f"case HNANodeType::NODE_{state_id}: return new hnl_{state_id}::HNLMonitor();\n"
                )
            wr(" default: abort();\n")
            wr(" };\n")
            wr("}\n")

    def _gen_do_step(self, hna):
        with self.new_file("do_step.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            wr("Verdict do_step(SliceTreeNode *node) {")
            wr(" switch (node->type) {")
            for state in hna.states():
                state_id = hna.get_state_id(state)
                wr(
                    f"case HNANodeType::NODE_{state_id}: return static_cast<hnl_{state_id}::HNLMonitor *>(node->monitor.get())->step();\n"
                )
            wr(" default: abort();\n")
            wr(" };\n")
            wr("}\n")

    def _gen_slice_node_dtor(self, hna):
        with self.new_file("slice-tree-node-dtor.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            wr(" switch (type) {")
            for state in hna.states():
                state_id = hna.get_state_id(state)
                wr(
                    f"case HNANodeType::NODE_{state_id}: delete static_cast<hnl_{state_id}::HNLMonitor *>(monitor.release()); break;\n"
                )
            wr(" default: abort();\n")
            wr(" };\n")

    def _generate_monitor(self, hna):
        with self.new_file("hna_node_types.h") as f:
            wr = f.write
            dump_codegen_position(wr)

            wr("enum class HNANodeType {\n")
            wr(f"INVALID = -1,\n")
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
                f"""
                SlicesTree() : root(new hnl_{init_id}::HNLMonitor(), HNANodeType::NODE_{init_id}) {{
                    /* _monitors.push_back(root.monitor.get()); */
                    _nodes.push_back(&root);
                    }}\n
                """
            )

        self._gen_slice_node_dtor(hna)

        self._gen_create_hnl_monitor(hna)
        self._gen_hna_transitions(hna)
        self._gen_do_step(hna)

    def _gen_hna_transitions(self, hna):
        with self.new_file("hna-next-slice.h") as f:
            wr = f.write
            dump_codegen_position(wr)

            wr(
                "HNANodeType nextSliceTreeNode(HNANodeType current_node, ActionEventType action) {\n"
            )
            wr("  switch (current_node) {\n")
            for state in hna.states():
                state_id = hna.get_state_id(state)
                wr(
                    f"  case HNANodeType::NODE_{state_id}:  return nextNode_{state_id}(action);\n"
                )
            wr("  default: abort();\n")
            wr("  };\n")
            wr("}\n\n")

            for state in hna.states():
                state_id = hna.get_state_id(state)
                wr(f"HNANodeType nextNode_{state_id}(ActionEventType action) {{\n")
                wr("  switch (action) {\n")
                T = hna.transitions(state=state)
                for action, t in T.items() if T else ():
                    assert len(t) == 1, "The automaton is non-deterministic"
                    wr(
                        f"  case ACTION_{action}: return HNANodeType::NODE_{hna.get_state_id(t[0].target)}; \n"
                    )
                wr("  default: return HNANodeType::INVALID;\n")
                wr("  };\n")
                wr("}\n")

    def generate(self, hna: HyperNodeAutomaton):
        """
        The top-level function to generate code
        """

        if not hna.is_deterministic():
            raise RuntimeError("The HNA is not deterministic")

        self._generate_events(hna)

        if self.args.gen_csv_reader:
            self._generate_csv_reader(hna)

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
        monitor_names = []
        for state in hna.states():
            hnl_id = hna.get_state_id(state)
            subdir = f"hnl-{hnl_id}"
            monitor_name = f"monitor_{hnl_id}"

            cmake_subdirs.append(subdir)
            monitor_names.append(monitor_name)

            embedding_data = {
                "monitor_name": monitor_name,
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
        self._generate_cmake(cmake_subdirs, monitor_names)

        # format the files if we have clang-format
        # FIXME: check clang-format properly instead of catching the exception
        try:
            for path in listdir(self.out_dir):
                if path.endswith(".h") or path.endswith(".cpp"):
                    run(["clang-format", "-i", f"{self.out_dir}/{path}"])
        except FileNotFoundError:
            pass
