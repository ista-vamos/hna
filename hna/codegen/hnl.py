from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin, basename

from hna.hnl.formula import IsPrefix, Quantifier, And, Or, Not
from hna.hnl.formula2automata import formula_to_automaton, compose_automata
from vamos_common.codegen.codegen import CodeGen

from pyeda.inter import bddvar


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
        self.templates_path = pathjoin(self_path, "templates/cpp")
        self._formula_to_automaton = {}
        self._automaton_to_formula = {}

        assert (
            self.args.csv_header
        ), "Give --csv-header, other methods not supported yet"
        self._event = [
            [s.strip() for s in event.split(":")]
            for event in self.args.csv_header.split(",")
        ]

    def _copy_common_files(self):
        files = [
            "trace.h",
            "trace.cpp",
            "traceset.h",
            "cmd.h",
            "cmd.cpp",
            "monitor.h",
            "monitor.cpp",
            "main.cpp",
            "csv.hpp",
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
                "@additional_cmake_definitions@": " ".join(
                    (d for d in self.args.cmake_defs)
                ),
                "@CMAKE_BUILD_TYPE@": build_type,
            },
        )

    def _generate_events(self):
        with self.new_file("events.h") as f:
            wr = f.write
            wr("#ifndef EVENTS_H_\n#define EVENTS_H_\n\n")
            wr("#include <iostream>\n\n")
            # wr("#include <cassert>\n\n")

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
            wr("auto it = row.begin();")
            for name, ty in self._event:
                wr(f"ev.{name} = it->get<{ty}>(); ++it;\n")

    def _generate_automaton_code(self, wrh, wrcpp):
        wrh("#pragma once\n\n")

    def _gen_bdd_from_formula(self, formula):
        atoms = {}

        def gen_bdd(F):
            """
            Recursively build BDD from the formula and create the mapping
            between atoms and BDD variables. Each atom represents a variable.
            """
            if F in atoms:
                return atoms[F]

            if isinstance(F, IsPrefix):
                v = bddvar(str(F))
                atoms[F] = v
                return v
            if isinstance(F, And):
                return gen_bdd(F.children[0]) & gen_bdd(F.children[1])
            if isinstance(F, Or):
                return gen_bdd(F.children[0]) | gen_bdd(F.children[1])
            if isinstance(F, Not):
                return ~gen_bdd(F.children[0])
            raise NotImplementedError(f"Not implemented operation: {F}")

        BDD = gen_bdd(formula.formula)
        if self.args.debug:
            with self.new_dbg_file("BDD.dot") as f:
                f.write(BDD.to_dot())

    def _generate_monitor(self, formula):
        # Generate BDD from the formula that will give us the order of evaluation
        # of atoms
        BDD = self._gen_bdd_from_formula(formula)

        for F, tmp in self._formula_to_automaton.items():
            num, A = tmp
            with self.new_file(f"atom-{num}.h") as fh:
                with self.new_file(f"atom-{num}.cpp") as fcpp:
                    self._generate_automaton_code(fh.write, fcpp.write)
            self.args.add_gen_files.append(f"atom-{num}.cpp")

    def generate_atomic_comparison_automaton(self, formula):
        num = len(self._formula_to_automaton) + 1

        alphabet = formula.constants()
        A1 = formula_to_automaton(formula.children[0], alphabet)
        A2 = formula_to_automaton(formula.children[1], alphabet)
        A = compose_automata(A1, A2)

        if self.args.debug:
            with self.new_dbg_file(f"aut-{num}-lhs.dot") as f:
                A1.to_dot(f)
            with self.new_dbg_file(f"aut-{num}-rhs.dot") as f:
                A2.to_dot(f)
            with self.new_dbg_file(f"aut-{num}.dot") as f:
                A.to_dot(f)

        self._formula_to_automaton[formula] = (num, A)
        self._automaton_to_formula[A] = (num, formula)

    def generate(self, formula):
        """
        The top-level function to generate code
        """

        self._generate_events()

        if self.args.gen_csv_reader:
            self._generate_csv_reader()

        def gen_automaton(F):
            if not isinstance(F, IsPrefix):
                return
            self.generate_atomic_comparison_automaton(F)

        formula.visit(gen_automaton)

        self._generate_monitor(formula)

        self._copy_common_files()
        # cmake generation should go at the end so that
        # it knows all the generated files
        self._generate_cmake()
