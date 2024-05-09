import os
from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin, basename
from subprocess import run

from pyeda.inter import bddvar

from hna.hnl.formula import IsPrefix, And, Or, Not, Constant
from hna.hnl.formula2automata import (
    formula_to_automaton,
    compose_automata,
    to_priority_automaton,
)
from vamos_common.codegen.codegen import CodeGen

import inspect


# This function dump the position from where it is called into the given file
def dump_codegen_position(f, end="\n"):
    parent_frame = inspect.getouterframes(inspect.currentframe())[1]
    msg = f"/* [CODEGEN]: {basename(parent_frame.filename)}:{parent_frame.function}:{parent_frame.lineno} */{end}"
    if callable(f):
        f(msg)
    else:
        f.write(msg)


def get_max_out_priority(automaton, state):
    return max(t.priority for t in automaton.transitions() if t.source == state)


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
            "verdict.h",
            "atommonitor.h",
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

    def _gen_bdd_from_formula(self, formula):
        """
        Generate BDD from the formula that will give us the order of evaluation
        of atoms
        """

        atoms = {}

        def gen_bdd(F):
            """
            Recursively build BDD from the formula and create the mapping
            between atoms and BDD variables. Each atom represents a variable.
            """
            if isinstance(F, IsPrefix):
                v = bddvar(str(F))
                atoms[v] = F
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

        return BDD, atoms

    def _generate_bdd_code(self, formula):
        BDD, atoms_map = self._gen_bdd_from_formula(formula)

        def bdd_to_action(bdd):
            if bdd.is_one():
                return "RESULT_TRUE"
            elif bdd.is_zero():
                return "RESULT_FALSE"

            F = atoms_map[bdd.top]
            return f"AUTOMATON_{self._formula_to_automaton[F][0]}"

        with self.new_file("actions.h") as f:
            f.write("#pragma once\n\n")
            dump_codegen_position(f)
            f.write("enum Action {\n")
            f.write("  INVALID      = 0,\n")
            f.write("  RESULT_TRUE  = -1,\n")
            f.write("  RESULT_FALSE = -2,\n")
            for num, A in self._formula_to_automaton.values():
                f.write(f"  AUTOMATON_{num} = {num},\n")
            f.write("};\n")
        # this is so stupid, but I just cannot get the variable
        # for the node, because PyEDA does not have getters for `_VARS`
        # dictionary. So I'm just generating sub-BDDs from which I
        # can get the root variable.
        with self.new_file("bdd-structure.h") as f:
            dump_codegen_position(f)
            f.write("/* AUTOMATON, ACTION_IF_TRUE, ACTION_IF_FALSE*/\n")
            f.write("Action BDD[][3] = {\n")
            seen = set()
            wbg = set()
            wbg.add(BDD)
            while wbg:
                bdd = wbg.pop()
                if bdd in seen or bdd.is_one() or bdd.is_zero():
                    continue
                seen.add(bdd)

                hi = bdd.restrict({bdd: 1})
                lo = bdd.restrict({bdd: 0})
                wbg.add(hi)
                wbg.add(lo)

                f.write(
                    f"  {{ {bdd_to_action(bdd)}, {bdd_to_action(hi)}, {bdd_to_action(lo)} }} ,\n"
                )

            f.write("};\n\n")

            dump_codegen_position(f)
            f.write(
                f"static constexpr Action INITIAL_ATOM = {bdd_to_action(BDD.top)};\n"
            )

    def _generate_hnlcfg(self, formula):
        with self.new_file("hnlcfg.h") as f:
            wr = f.write
            wr("#pragma once\n\n")
            wr('#include "actions.h"\n\n')
            wr('#include "trace.h"\n\n')
            wr("class AtomMonitor;\n\n")
            dump_codegen_position(wr)
            wr("struct HNLCfg {\n")
            wr("  /* traces */\n")
            for q in formula.quantifier_prefix:
                wr(f"  const Trace *{q.var};\n")
            wr("\n  /* Currently evaluated atom automaton */\n")
            wr(f"  Action state;\n\n")
            wr("  /* The monitor this configuration waits for */\n")
            wr("  AtomMonitor *monitor{nullptr};\n\n")
            wr(f"  HNLCfg(")
            for q in formula.quantifier_prefix:
                wr(f"const Trace *{q.var}, ")
            wr("Action init_state)\n  : ")
            for q in formula.quantifier_prefix:
                wr(f"{q.var}({q.var}), ")
            wr("state(init_state) {}\n")
            wr("};\n")

    def _generate_create_cfgs(self, formula):
        N = len(formula.quantifier_prefix)
        with self.new_file("createcfgs.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            wr("/* the code that precedes this defines a variable `t1` */\n\n")
            for i in range(2, N + 1):
                wr(f"for (const auto &t{i}_it : _traces) {{\n")
                wr(f"  const auto *t{i} = t{i}_it.get();\n")

            dump_codegen_position(wr)
            wr("\n  /* Create the configuration */\n")
            wr("\n  _cfgs.emplace_back(")
            for i in range(1, N + 1):
                wr(f"t{i}, ")
            wr("INITIAL_ATOM);\n\n")
            wr(
                "_cfgs.back().monitor = createAtomMonitor(INITIAL_ATOM, _cfgs.back());\n"
            )

            for i in range(2, len(formula.quantifier_prefix) + 1):
                wr("}\n")

    def _generate_atom_monitor(self):
        with self.new_file("createatommonitor.h") as f:
            dump_codegen_position(f)
            f.write("switch(monitor_type) {\n")
            for F, tmp in self._formula_to_automaton.items():
                num, A = tmp
                f.write(
                    f"case AUTOMATON_{num}: monitor = new AtomMonitor{num}(hnlcfg); break;\n"
                )
            f.write("default: abort();\n")
            f.write("}\n\n")

    def _generate_monitor(self, formula):
        self._generate_bdd_code(formula)
        self._generate_hnlcfg(formula)
        self._generate_create_cfgs(formula)
        self._generate_automata_code()
        self._generate_atom_monitor()

    def _generate_automata_code(self):
        for F, tmp in self._formula_to_automaton.items():
            num, A = tmp
            with self.new_file(f"atom-{num}.h") as fh:
                with self.new_file(f"atom-{num}.cpp") as fcpp:
                    self._generate_automaton_code(fh.write, fcpp.write, F, num, A)
            self.args.add_gen_files.append(f"atom-{num}.cpp")

        with self.new_file("atoms.h") as f:
            f.write("#pragma once\n\n")
            dump_codegen_position(f)
            for F, tmp in self._formula_to_automaton.items():
                num, A = tmp
                f.write(f'#include "atom-{num}.h"\n')

        with self.new_file("do_step.h") as f:
            dump_codegen_position(f)
            f.write("switch (M->type()) {")
            for F, tmp in self._formula_to_automaton.items():
                num, A = tmp
                f.write(
                    f"  case {num}: return static_cast<AtomMonitor{num}*>(M)->step();"
                )
            f.write("  default: abort(); ")
            f.write("}")

    def _generate_automaton_code(
        self, wrh, wrcpp, atom_formula: IsPrefix, num, automaton
    ):
        wrh("#pragma once\n\n")
        dump_codegen_position(wrh)
        wrh('#include "atommonitor.h"\n\n')
        dump_codegen_position(wrh)
        wrh(f"/* {atom_formula}*/\n")
        wrh(f"class AtomMonitor{num} : public AtomMonitor {{\n")
        wrh("public:\n")
        t1 = atom_formula.children[0].trace_variables()
        t2 = atom_formula.children[1].trace_variables()
        assert len(t1) == 1, str(t1)
        assert len(t2) == 1, str(t2)
        t1 = t1[0].name
        t2 = t2[0].name
        wrh(f"AtomMonitor{num}(HNLCfg& cfg);\n\n")
        wrh(f"Verdict step(unsigned num = 0);\n\n")
        wrh("};\n")

        wrcpp(f'#include "atom-{num}.h"\n\n')
        dump_codegen_position(wrcpp)
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(HNLCfg& cfg) \n  : AtomMonitor(AUTOMATON_{num}, cfg.{t1}, cfg.{t2}) {{\n\n"
        )
        # create the initial configuration
        priorities = list(set(t.priority for t in automaton.transitions()))
        priorities.sort(reverse=True)

        assert (
            len(automaton.initial_states()) == 1
        ), f"Automaton {num} has multiple initial states"
        wrcpp(
            f"_cfgs.emplace_back({automaton.get_state_id(automaton.initial_states()[0])}, 0, 0, {priorities[0]});\n"
        )
        wrcpp("}\n\n")

        wrcpp(f"/* THE AUTOMATON */\n")
        for state in automaton.states():
            wrcpp(f"/* {state} */\n")
        wrcpp("/* --- */\n")
        for t in automaton.transitions():
            wrcpp(f"/* {t} */\n")
        wrcpp("/* --- */\n\n")

        dump_codegen_position(wrcpp)
        assert (
            len(automaton.accepting_states()) > 0
        ), f"Automaton {num} has no accepting states"
        wrcpp("static inline bool state_is_accepting(State s) {")
        wrcpp(" switch (s) {")
        for i in (automaton.get_state_id(s) for s in automaton.accepting_states()):
            wrcpp(f" case {i}: return true;")
        wrcpp(" default: return false;")
        wrcpp(" };")
        wrcpp("}\n\n")

        dump_codegen_position(wrcpp)
        wrcpp(
            "// FIXME: only modify configuration if it has a single possible successor\n"
        )
        wrcpp(f"Verdict AtomMonitor{num}::step(unsigned num) {{\n")
        wrcpp(
            f"""
            _new_cfgs.clear();
            
            for (auto& cfg : _cfgs) {{
                auto *ev1 = t1->get(cfg.p1);
                if (!ev1)
                    continue;
                auto *ev2 = t2->get(cfg.p2);
                if (!ev2)
                    continue;
                    
                if (ev1 == TRACE_END && ev2 == TRACE_END) {{
                    if (state_is_accepting(cfg.state)) {{
                        return Verdict::TRUE;
                    }} else {{
                      /* FIXME: DROP CONFIGURATION */
                      abort();
                    }}
                }}
                
                std::cerr << "Atom {num}@ (" << cfg.state  << "/" << cfg.priority << ", " << cfg.p1 << ", " << cfg.p2 << "): "
                                             << *ev1 << ", " << *ev2 << "\\n";
                /* WE HAVE BOTH EVENTS */
        """
        )
        lvar = atom_formula.children[0].program_variables()
        rvar = atom_formula.children[1].program_variables()
        assert len(lvar) == len(rvar) == 1, (lvar, rvar)
        lvar, rvar = lvar[0].name, rvar[0].name

        # we assume when we have a transition with a priority p,
        # then we have transitions with all priorities 0 ... p.
        # This is important because then in the code we just decrement
        # the priority counter by one instead of looking up the next priority
        # to test.
        assert priorities == list(reversed(range(0, priorities[0] + 1))), priorities

        wrcpp(f"  bool matched;\n")
        dump_codegen_position(wrcpp)
        if len(automaton.states()) == 1:
            wrcpp("/* FIXME: do not generate the switch for a single state */\n")
        wrcpp(f"  switch (cfg.state) {{\n")
        for state in automaton.states():
            transitions = [t for t in automaton.transitions() if t.source == state]
            wrcpp(f" /* {state} */\n ")
            wrcpp(f" case {automaton.get_state_id(state)}:\n ")
            if not transitions:
                wrcpp("abort(); /* FIXME: DROP CFG */\n\n")
                continue

            if len(priorities) == 1:
                wrcpp("/* FIXME: do not generate the switch for a priority */\n")
            wrcpp(f"  switch (cfg.priority) {{")
            for prio in priorities:
                ptransitions = [t for t in transitions if t.priority == prio]
                if not ptransitions:
                    continue
                wrcpp(f" case {prio}:\n ")
                wrcpp(f"  matched = false;\n ")
                # FIXME: we could still optimize that to have less branching
                ### Handle epsilon steps
                for t in (
                    t
                    for t in ptransitions
                    if t.label[0].is_epsilon() and t.label[1].is_epsilon()
                ):
                    wrcpp(f" /* {t} */\n ")
                    dump_codegen_position(wrcpp)
                    wrcpp(f"   matched = true;\n ")
                    wrcpp(
                        f"   _new_cfgs.emplace_back({automaton.get_state_id(t.target)}, cfg.p1, cfg.p2, {get_max_out_priority(automaton, t.target)});\n "
                    )
                    wrcpp(
                        f'   std::cerr << "  --> new (" << _new_cfgs.back().state  << "/" <<  _new_cfgs.back().priority << ", " <<  _new_cfgs.back().p1 << ", " <<  _new_cfgs.back().p2 << ")\\n";'
                    )

                ### Handle left-epsilon steps
                tmp = [
                    t
                    for t in ptransitions
                    if t.label[0].is_epsilon() and not t.label[1].is_epsilon()
                ]
                if tmp:
                    dump_codegen_position(wrcpp)
                    wrcpp(f" if (ev2 != TRACE_END) {{\n ")
                    for t in tmp:
                        wrcpp(f" /* {t} */\n ")
                        wrcpp(f" if (ev2->{rvar} == {t.label[1]}) {{")
                        wrcpp(f"   matched = true;\n ")
                        wrcpp(
                            f"   _new_cfgs.emplace_back({automaton.get_state_id(t.target)}, cfg.p1, cfg.p2 + 1, {get_max_out_priority(automaton, t.target)});\n "
                        )
                        wrcpp(
                            f'   std::cerr << "  --> new (" << _new_cfgs.back().state  << "/" <<  _new_cfgs.back().priority << ", " <<  _new_cfgs.back().p1 << ", " <<  _new_cfgs.back().p2 << ")\\n";'
                        )

                        wrcpp("}\n")
                    wrcpp("}\n")

                ### Handle right-epsilon steps
                tmp = [
                    t
                    for t in ptransitions
                    if not t.label[0].is_epsilon() and t.label[1].is_epsilon()
                ]
                if tmp:
                    dump_codegen_position(wrcpp)
                    wrcpp(f" if (ev1 != TRACE_END) {{\n ")
                    for t in tmp:
                        wrcpp(f" /* {t} */\n ")
                        wrcpp(f" if (ev1->{lvar} == {t.label[0]}) {{")
                        wrcpp(f"   matched = true;\n ")
                        wrcpp(
                            f"  _new_cfgs.emplace_back({automaton.get_state_id(t.target)}, cfg.p1 + 1, cfg.p2, {get_max_out_priority(automaton, t.target)});\n "
                        )
                        wrcpp(
                            f'   std::cerr << "  --> new (" <<_new_cfgs.back().state  << "/" << _new_cfgs.back().priority << ", " << _new_cfgs.back().p1 << ", " << _new_cfgs.back().p2 << ")\\n";'
                        )
                        wrcpp("}\n")
                    wrcpp("}\n")

                ### Handle letters
                tmp = [
                    t
                    for t in ptransitions
                    if not t.label[0].is_epsilon() and not t.label[1].is_epsilon()
                ]
                if tmp:
                    dump_codegen_position(wrcpp)
                    wrcpp(f" if (ev1 != TRACE_END && ev2 != TRACE_END) {{\n ")
                    for t in tmp:
                        wrcpp(f" /* {t} */\n ")
                        wrcpp(
                            f" if (ev1->{lvar} == {t.label[0]} && ev2->{rvar} == {t.label[1]}) {{"
                        )
                        wrcpp(f"   matched = true;\n ")
                        wrcpp(
                            f"  _new_cfgs.emplace_back({automaton.get_state_id(t.target)}, cfg.p1 + 1, cfg.p2 + 1, {get_max_out_priority(automaton, t.target)});\n "
                        )
                        wrcpp(
                            f'   std::cerr << "  --> new (" <<_new_cfgs.back().state  << "/" << _new_cfgs.back().priority << ", " << _new_cfgs.back().p1 << ", " << _new_cfgs.back().p2 << ")\\n";'
                        )
                        wrcpp("}\n")
                    wrcpp("}\n")

                dump_codegen_position(wrcpp)
                wrcpp("if (matched) { abort(); /* DROP CFG */ break; }")
                if prio > 0:
                    wrcpp(
                        "else { --cfg.priority;\n [[fallthrough]]; /* fall through */ }"
                    )
                else:
                    wrcpp("else { abort(); /* DROP CFG */; break; }")
            wrcpp(f"  default : abort();\n ")
            wrcpp("   };\n")
            wrcpp(f" break;\n ")
        wrcpp(f" default : abort();\n ")
        wrcpp("  };\n")
        wrcpp(" }\n")
        wrcpp(" return Verdict::UNKNOWN;\n")
        wrcpp("}\n")

    def _aut_to_html(self, filename, A):
        """
        Dump automaton into HTML + JS page, an alternative to graphviz
        that should handle the graphs more nicely.
        """
        assert filename.endswith(".html"), filename
        with self.new_dbg_file(filename) as f:
            self.input_file(f, "../partials/html/graph-view-start.html")
            f.write("elements: ")
            A.to_json(f)
            f.write(",")
            self.input_file(f, "../partials/html/graph-view-end.html")

    def generate_atomic_comparison_automaton(self, formula, alphabet):
        num = len(self._formula_to_automaton) + 1

        A1 = formula_to_automaton(formula.children[0], alphabet)
        A2 = formula_to_automaton(formula.children[1], alphabet)
        A = compose_automata(A1, A2, alphabet)
        Ap = to_priority_automaton(A)

        if self.args.debug:
            with self.new_dbg_file(f"aut-{num}-lhs.dot") as f:
                A1.to_dot(f)
            with self.new_dbg_file(f"aut-{num}-rhs.dot") as f:
                A2.to_dot(f)
            with self.new_dbg_file(f"aut-{num}.dot") as f:
                A.to_dot(f)
            with self.new_dbg_file(f"aut-{num}-prio.dot") as f:
                Ap.to_dot(f)

            self._aut_to_html(f"aut-{num}-lhs.html", A1)
            self._aut_to_html(f"aut-{num}-rhs.html", A2)
            self._aut_to_html(f"aut-{num}.html", A)
            self._aut_to_html(f"aut-{num}-prio.html", Ap)

        self._formula_to_automaton[formula] = (num, Ap)
        self._automaton_to_formula[Ap] = (num, formula)

        assert len(Ap.accepting_states()) > 0, f"Automaton has no accepting states"
        assert len(Ap.initial_states()) > 0, f"Automaton has no initial states"

    def generate(self, formula):
        """
        The top-level function to generate code
        """

        self._generate_events()

        if self.args.gen_csv_reader:
            self._generate_csv_reader()

        if not self.args.alphabet:
            print(
                "No alphabet given, using constants from the formula: ",
                formula.constants(),
            )
            alphabet = formula.constants()
        else:
            alphabet = [Constant(a) for a in self.args.alphabet]

        def gen_automaton(F):
            if not isinstance(F, IsPrefix):
                return
            self.generate_atomic_comparison_automaton(F, alphabet)

        formula.visit(gen_automaton)

        self._generate_monitor(formula)

        self._copy_common_files()
        # cmake generation should go at the end so that
        # it knows all the generated files
        self._generate_cmake()

        # format the files if we have clang-format
        # FIXME: check clang-format properly instead of catching the exception
        try:
            for path in os.listdir(self.out_dir):
                if path.endswith(".h") or path.endswith(".cpp"):
                    run(["clang-format", "-i", f"{self.out_dir}/{path}"])
        except FileNotFoundError:
            pass
