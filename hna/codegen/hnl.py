import random
from os import readlink, listdir, makedirs
from os.path import abspath, dirname, islink, join as pathjoin, basename
from subprocess import run

from pyeda.inter import bddvar

from hna.automata.automaton import Automaton
from hna.codegen.common import dump_codegen_position
from hna.hnl.formula import (
    IsPrefix,
    And,
    Or,
    Not,
    Constant,
    Function,
    ForAll,
    TraceVariable,
    PrenexFormula,
)
from hna.hnl.formula2automata import (
    formula_to_automaton,
    compose_automata,
    to_priority_automaton,
    TupleLabel,
)
from vamos_common.codegen.codegen import CodeGen


# def paths(A: Automaton):
#     """
#     Generate (prefixes of) paths from the automaton.
#     Not very efficient, but we don't care that much.
#     """
#     P = [[t] for ts in A.transitions(A.initial_states()[0]).values() for t in ts]
#     print(P)
#     while True:
#         new_P = []
#         for path in P:
#             for l, ts in A.transitions(path[-1].target).items():
#                 for t in ts:
#                     tmp = path + [t]
#                     yield tmp
#                     new_P.append(tmp)
#         P = new_P
#


def random_path(A: Automaton, length):
    T = [t for ts in A.transitions(A.initial_states()[0]).values() for t in ts]
    path = [T[random.randrange(0, len(T))]]
    l = 1

    while l < length:
        T = A.transitions(path[-1].target)
        if T is None:  # we reached a state without transitions
            return path

        T = [t for ts in T.values() for t in ts]
        path.append(T[random.randrange(0, len(T))])
        l += 1
    return path


def path_is_accepting(A: Automaton, path):
    """
    Return if the path is accepting -- the last state
    must be accepting or from that state an accepting state
    must be reachable via epsilon steps.
    """
    state = path[-1].target
    states, wbg = set(), set()
    states.add(state)
    wbg.add(state)

    while wbg:
        state = wbg.pop()
        if A.is_accepting(state):
            return True
        # get all transitions from this state
        epsilonT = [
            t
            for _, tt in A.transitions(state, default=dict()).items()
            for t in tt
            if t.label[0].is_epsilon() and t.label[1].is_epsilon()
        ]
        priorities = list(set(t.priority for t in epsilonT))
        priorities.sort(reverse=True)

        # process epsilon transitions in the order of their priority
        for prio in priorities:
            T = [t for t in epsilonT if prio == t.priority]
            if T:
                for t in T:
                    if t.target not in states:
                        states.add(t.target)
                        wbg.add(t.target)
                break
    return False


def get_max_out_priority(automaton, state):
    return max(t.priority for t in automaton.transitions() if t.source == state)


def traces_positions(t1_pos, N):
    """
    Generate sequence of numbers 2, 3, 4, ... N
    and 1 with 1 on the `t1_pos`.
    """
    for n, i in enumerate(range(2, N + 1)):
        if n + 1 == t1_pos:
            yield 1
        yield i
    if t1_pos == N:
        yield 1


class CodeGenCpp(CodeGen):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.
    """

    def __init__(self, args, ctx, out_dir=None, namespace=None):
        super().__init__(args, ctx, out_dir)

        self_path = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_path, "templates/cpp/hnl")
        self._namespace = namespace
        self._formula_to_automaton = {}
        self._automaton_to_formula = {}
        self._add_gen_files = []
        self._atoms_files = []
        self._submonitors_dirs = {}
        self._submonitors = []

        assert (
            self.args.csv_header
        ), "Give --csv-header, other methods not supported yet"
        self._event = [
            [s.strip() for s in event.split(":")]
            for event in self.args.csv_header.split(",")
        ]

    def copy_files(self, files):
        for f in files:
            if f not in self.args.overwrite_file:
                self.copy_file(f)

        for f in self.args.cpp_files:
            self.copy_file(f)

    def _copy_common_files(self):
        files = [
            "../monitor.h",
            "../hnl-monitor-base.h",
            "../cmd.h",
            "../cmd.cpp",
            "../stream.h",
            "../trace.h",
            "../trace.cpp",
            "../traceset.h",
            "../traceset.cpp",
            "../tracesetview.h",
            "../tracesetview.cpp",
            "../sharedtraceset.h",
            "../sharedtraceset.cpp",
            "../verdict.h",
            "../atom-base.h",
            "../atom-evaluation-state.h",
            # XXX: do this only when functions are used
            "../function.h",
        ]
        self.copy_files(files)

    def generate_cmake(self, overwrite_keys=None, embedded=False):
        """
        `embedded` is True if the HNL monitor is a subdirectory in some other project
        """
        from config import vamos_buffers_DIR

        build_type = self.args.build_type
        if not build_type:
            build_type = '"Debug"' if self.args.debug else "Release"

        values = {
            "@vamos-buffers_DIR@": vamos_buffers_DIR,
            "@additional_sources@": " ".join(
                (
                    basename(f)
                    for f in self.args.cpp_files
                    + self.args.add_gen_files
                    + self._add_gen_files
                )
            ),
            "@atoms_sources@": " ".join((basename(f) for f in self._atoms_files)),
            "@additional_cflags@": " ".join((d for d in self.args.cflags)),
            "@CMAKE_BUILD_TYPE@": build_type,
            "@MONITOR_NAME@": '""',
            "@ADD_NESTED_MONITORS@": "\n".join(
                (
                    f"add_subdirectory({submon_dir})"
                    for submon_dir in self._submonitors_dirs.values()
                )
            ),
            "@submonitors_libs@": " ".join(self._submonitors),
        }
        if overwrite_keys:
            values.update(overwrite_keys)

        if embedded:
            cmakelists = "CMakeLists-embedded.txt.in"
        else:
            cmakelists = "CMakeLists.txt.in"
        self.gen_config(cmakelists, "CMakeLists.txt", values)

    def _generate_events(self):
        with self.new_file("events.h") as f:
            wr = f.write
            wr("#ifndef EVENTS_H_\n#define EVENTS_H_\n\n")
            wr("#include <iostream>\n")
            wr("#include <cstdint>\n\n")
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
        self.copy_file("../csvreader.h")
        self.copy_file("../csvreader.cpp")
        self._add_gen_files.append("csvreader.cpp")

        with self.new_file("csvreader-aux.h") as f:
            dump_codegen_position(f)

        with self.new_file("read_csv_event.h") as f:
            wr = f.write
            wr(f"int ch;\n\n")
            for n, tmp in enumerate(self._event):
                name, ty = tmp
                # wr(f"char action[{max_len_action_name}];\n\n")
                wr(f"_stream >> ev.{name};\n")
                wr("if (_stream.fail()) {")
                if n == 0:  # assume this is the header
                    wr(" if (_events_num_read == 0) {\n")
                    wr("   _stream.clear(); // assume this is the header\n")
                    wr("   // FIXME: check that the header matches the events \n")
                    wr("   // ignore the rest of the line and try with the next one\n")
                    wr(
                        "   _stream.ignore(std::numeric_limits<std::streamsize>::max(), '\\n');\n"
                    )
                    wr(f"   _stream >> ev.{name};\n")
                    wr("    if (_stream.fail()) {")
                    wr(
                        f'    std::cerr << "Failed reading column \'{name}\' on line " << _events_num_read + 1 << "\\n";'
                    )
                    wr("    abort();")
                    wr("  }")
                    wr("} else {")
                    wr(
                        f'    std::cerr << "Failed reading column \'{name}\' on line " << _events_num_read + 1 << "\\n";'
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
            return f"ATOM_{self._formula_to_automaton[F][0]}"

        with self.new_file("hnl-state.h") as f:
            ns = self._namespace or ""
            f.write(
                f"""
            #ifndef _HNL_STATE_H__{ns}
            #define _HNL_STATE_H__{ns}
            """
            )
            if self._namespace:
                f.write(f"namespace {self._namespace} {{\n\n")
            dump_codegen_position(f)
            f.write("enum HNLEvaluationState {\n")
            f.write("  INVALID      = 0,\n")
            f.write("  RESULT_TRUE  = -1,\n")
            f.write("  RESULT_FALSE = -2,\n")
            for num, A in self._formula_to_automaton.values():
                f.write(f"  ATOM_{num} = {num},\n")
            f.write("};\n")
            if self._namespace:
                f.write(f"}} // namespace {self._namespace}\n\n")
            f.write("#endif\n")

        # this is so stupid, but I just cannot get the variable
        # for the node, because PyEDA does not have getters for `_VARS`
        # dictionary. So I'm just generating sub-BDDs from which I
        # can get the root variable.
        with self.new_file("bdd-structure.h") as f:
            dump_codegen_position(f)
            f.write("/* ATOM, ACTION_IF_TRUE, ACTION_IF_FALSE*/\n")
            f.write("constexpr HNLEvaluationState BDD[][3] = {\n")
            f.write("  {INVALID, INVALID, INVALID},\n")
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
                f"static constexpr HNLEvaluationState INITIAL_ATOM = {bdd_to_action(BDD.top)};\n"
            )

    def _generate_hnlinstances(self, formula):
        with self.new_file("hnl-instance.h") as f:
            wr = f.write
            ns = self._namespace or ""
            wr(
                f"""
            #ifndef _HNL_INSTANCE_H__{ns}
            #define _HNL_INSTANCE_H__{ns}
            """
            )
            wr("#include <cassert>\n\n")
            wr('#include "hnl-state.h"\n')
            wr('#include "trace.h"\n\n')
            if self._namespace:
                wr(f"namespace {self._namespace} {{\n\n")
            wr("class AtomMonitor;\n\n")
            dump_codegen_position(wr)
            wr("struct HNLInstance {\n")
            wr("  /* traces */\n")
            for q in formula.quantifier_prefix:
                wr(f"  Trace *{q.var};\n")
            wr("\n  /* Currently evaluated atom automaton */\n")
            wr(f"  HNLEvaluationState state;\n\n")
            wr("  /* The monitor this configuration waits for */\n")
            wr("  AtomMonitor *monitor{nullptr};\n\n")
            wr(f"  HNLInstance(")
            for q in formula.quantifier_prefix:
                wr(f"Trace *{q.var}, ")
            wr("HNLEvaluationState init_state)\n  : ")
            for q in formula.quantifier_prefix:
                wr(f"{q.var}({q.var}), ")
            wr("state(init_state) { assert(state != INVALID); }\n")
            wr("};\n\n")
            if self._namespace:
                wr(f" }} // namespace {self._namespace}\n")
            wr("#endif\n")

    def _generate_create_instances(self, formula):
        N = len(formula.quantifier_prefix)
        with self.new_file("create-instances.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            wr("/* the code that precedes this defines a variable `t1` */\n\n")
            for i in range(2, N + 1):
                wr(f"for (auto &[t{i}_id, t{i}_ptr] : _traces) {{\n")
                wr(f"  auto *t{i} = t{i}_ptr.get();\n")

            self._gen_create_instance(N, formula, wr)

    def _gen_create_instance(self, N, formula, wr):
        wr(
            """
        /* Create the instances
        
           XXX: Maybe it could be more efficient to just have a hash map 
           XXX: and check if we have generated the combination (instead of checking
           XXX: those conditions) */
        """
        )

        dump_codegen_position(wr)
        for t1_pos in range(1, N + 1):
            # compute the condition to avoid repeating the combinations
            # of traces
            conds = []
            # FIXME: generate the matrix instead of generating the rows again and again
            posrow = list(traces_positions(t1_pos, N))
            for r in range(1, t1_pos):
                # these traces cannot be the same
                diffs = set()
                for i1, i2 in zip(
                    posrow[r - 1 : t1_pos],
                    list(traces_positions(r, N))[r - 1 : t1_pos],
                ):
                    diffs.add((i1, i2) if i1 < i2 else (i2, i1))
                c = "||".join((f"t{i1} != t{i2}" for i1, i2 in diffs))
                conds.append(f"({c})" if len(diffs) > 1 else c)
            cond = "&&".join(conds) if conds else "true"
            wr(f"if ({cond}) {{")
            dump_codegen_position(wr)
            wr("\n  _instances.emplace_back(new HNLInstance{")
            for i in traces_positions(t1_pos, N):
                wr(f"t{i}, ")
            wr("INITIAL_ATOM});\n")
            wr("++stats.num_instances;\n\n")
            wr(
                "_instances.back()->monitor = createAtomMonitor(INITIAL_ATOM, *_instances.back().get());\n"
            )
            dump_codegen_position(wr)
            ns = f"{self._namespace}::" if self._namespace else ""
            wr("#ifdef DEBUG_PRINTS\n")
            wr(f'std::cerr << "{ns}HNLInstance[init"')
            for i in traces_positions(t1_pos, N):
                wr(f' << ", " << t{i}->id()')
            wr('<< "]\\n";\n')
            wr("#endif /* !DEBUG_PRINTS */\n")
            wr("}\n")
        for i in range(2, len(formula.quantifier_prefix) + 1):
            wr("}\n")

    def _generate_create_instances_function_mon(self, embedding_data):
        is_fun_monitor = embedding_data.get("is_function_monitor") is not None
        ns = f"{self._namespace}::" if self._namespace else ""

        with self.new_file("create-instances-left.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            if is_fun_monitor:
                wr("/* the code that precedes this defines a variable `tl` */\n\n")
                wr(
                    f"""
                for (auto &[tr_id, tr] : _traces_r) {{
                    _instances.emplace_back(new HNLInstance{{tl, tr, INITIAL_ATOM}});
                    ++stats.num_instances;
                    
                    _instances.back()->monitor =
                        createAtomMonitor(INITIAL_ATOM, *_instances.back().get());
                    #ifdef DEBUG_PRINTS
                    std::cerr << "{ns}HNLInstance[init" << ", " << tl->id() << ", " << tr->id() << "]\\n";
                    #endif /* !DEBUG_PRINTS */
                """
                )
                wr("}\n")
            else:
                wr("(void)tl; abort(); /* this function should be never called */\n")

        with self.new_file("create-instances-right.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            if is_fun_monitor:
                wr("/* the code that precedes this defines a variable `tr` */\n\n")
                wr(
                    f"""
                for (auto &[tl_id, tl] : _traces_l) {{
                    _instances.emplace_back(new HNLInstance{{tl, tr, INITIAL_ATOM}});
                    ++stats.num_instances;

                    _instances.back()->monitor =
                        createAtomMonitor(INITIAL_ATOM, *_instances.back().get());
                        
                    #ifdef DEBUG_PRINTS
                    std::cerr << "{ns}HNLInstance[init" << ", " << tl->id() << ", " << tr->id() << "]\\n";
                    #endif /* !DEBUG_PRINTS */
                }}
                """
                )

            else:
                wr("(void)tr; abort(); /* this function should be never called */\n")

    def _generate_atom_monitor(self):
        with self.new_file("create-atom-monitor.h") as f:
            dump_codegen_position(f)
            f.write("switch(monitor_type) {\n")
            for F, tmp in self._formula_to_automaton.items():
                num, A = tmp
                lf, rf = F.children[0].functions(), F.children[1].functions()
                lf = f", function_{lf[0].name}.get()" if lf else ""
                rf = f", function_{rf[0].name}.get()" if rf else ""
                f.write(
                    f"case ATOM_{num}: monitor = new AtomMonitor{num}(instance{lf}{rf}); break;\n"
                )
            f.write("default: abort();\n")
            f.write("}\n\n")

    def _generate_monitor(self, formula, alphabet, embedding_data):
        self._generate_bdd_code(formula)
        self._generate_hnlinstances(formula)
        self._generate_create_instances(formula)
        self._generate_create_instances_function_mon(embedding_data)
        self._generate_automata_code(alphabet)
        self._generate_atom_monitor()

    def _generate_automata_code(self, alphabet):
        # NOTE: this must preced generating the `atom-*` files,
        # because it initializes the `self._submonitors_dirs`
        self._generate_submonitors(alphabet)

        for F, tmp in self._formula_to_automaton.items():
            num, A = tmp
            with self.new_file(f"atom-{num}.h") as fh:
                if F.functions():
                    self._generate_atom_with_funs_header(F, num, fh.write)
                else:
                    self._generate_atom_header(F, A, num, fh.write)

            with self.new_file(f"atom-{num}.cpp") as fcpp:
                if F.functions():
                    self._generate_atom_with_funs(fcpp.write, F, num)
                else:
                    self._generate_atom(fcpp.write, F, num, A)
            self._atoms_files.append(f"atom-{num}.cpp")

        with self.new_file("atoms.h") as f:
            ns = self._namespace or ""
            f.write(
                f"""
            #ifndef _ATOMS_H__{ns}
            #define _ATOMS_H__{ns}
            """
            )
            dump_codegen_position(f)
            for F, tmp in self._formula_to_automaton.items():
                num, A = tmp
                f.write(f'#include "atom-{num}.h"\n')
            f.write("#endif\n")

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

    def _generate_submonitors(self, alphabet):
        assert self._formula_to_automaton, "Formulas not translated to automata"
        for F, tmp in self._formula_to_automaton.items():
            num, A = tmp
            if not F.functions():
                continue
            submon_dir = f"mon-atom-{num}"
            assert num not in self._submonitors_dirs
            self._submonitors_dirs[num] = submon_dir
            self._submonitors.append(f"hnlatom{num}")
            nested_mon = CodeGenCpp(
                self.args,
                ctx=None,
                out_dir=f"{self.out_dir}/{submon_dir}",
                namespace=f"atom{num}",
            )

            embedding_data = {
                "monitor_name": f"atom{num}",
                "tests": True,
                "is_function_monitor": True,
            }
            subs = {}
            lf, rf = F.children[0].functions(), F.children[1].functions()
            if lf:
                assert len(lf) == 1, lf
                tr1 = TraceVariable(f"tr_f1_{lf[0].name}")
                subs[lf[0]] = tr1
            else:
                assert len(F.children[0].trace_variables()) == 1, F.children[0]
                tr1 = F.children[0].trace_variables()[0]
            if rf:
                assert len(rf) == 1, rf
                tr2 = TraceVariable(f"tr_f2_{rf[0].name}")
                subs[rf[0]] = tr2
            else:
                assert len(F.children[1].trace_variables()) == 1, F.children[1]
                tr2 = F.children[1].trace_variables()[0]

            formula = PrenexFormula([ForAll(tr1), ForAll(tr2)], Not(F.substitute(subs)))
            nested_mon.generate_embedded(formula, alphabet, embedding_data)

    def _generate_atom(self, wrcpp, atom_formula: IsPrefix, num, automaton):

        p1 = atom_formula.children[0].program_variables()
        p2 = atom_formula.children[1].program_variables()
        assert len(p1) <= 1, str(p1)
        assert len(p2) <= 1, str(p2)
        t1 = p1[0].trace.name if p1 else None
        t2 = p2[0].trace.name if p2 else None
        if not (t1 or t2):
            raise NotImplementedError("This case is unsupported yet")
        if not t1:
            raise NotImplementedError("This case is unsupported yet")

        wrcpp(f'#include "atom-{num}.h"\n\n')
        if self._namespace:
            wrcpp(f"using namespace {self._namespace};\n\n")
        dump_codegen_position(wrcpp)
        t1_instance = f"instance.{t1}" if t1 else "nullptr"
        t2_instance = f"instance.{t2}" if t2 else "nullptr"
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(HNLInstance& instance) \n  : RegularAtomMonitor(ATOM_{num}, {t1_instance}, {t2_instance}) {{\n\n"
        )
        # create the initial configuration
        priorities = list(set(t.priority for t in automaton.transitions()))
        priorities.sort(reverse=True)

        assert (
            len(automaton.initial_states()) == 1
        ), f"Automaton {num} has multiple initial states"
        wrcpp(
            f"_cfgs.emplace_back({automaton.get_state_id(automaton.initial_states()[0])}, 0, 0);\n"
        )
        wrcpp("}\n\n")

        wrcpp(f"/* THE AUTOMATON FOR THE ATOM */\n")
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

        self.gen_handle_state(num, atom_formula, automaton, priorities, wrcpp)

        dump_codegen_position(wrcpp)
        wrcpp(
            "// FIXME: only modify configuration if it has a single possible successor\n"
        )

        wrcpp(
            f"void AtomMonitor{num}::_step(EvaluationState &cfg, const Event *ev1, const Event *ev2) {{\n"
        )
        # we assume when we have a transition with a priority p,
        # then we have transitions with all priorities 0 ... p.
        # This is important because then in the code we just decrement
        # the priority counter by one instead of looking up the next priority
        # to test.
        assert priorities == list(reversed(range(0, priorities[0] + 1))), priorities

        dump_codegen_position(wrcpp)
        if len(automaton.states()) == 1:
            wrcpp("/* FIXME: do not generate the switch for a single state */\n")
        wrcpp(f"  switch (cfg.state) {{\n")
        for state in automaton.states():
            transitions = [t for t in automaton.transitions() if t.source == state]
            wrcpp(f" /* {state} */\n ")
            wrcpp(f" case {automaton.get_state_id(state)}:\n ")
            if not transitions:
                wrcpp("/* DROP CFG */\n\n")
                continue
            else:
                wrcpp(f"stepState_{automaton.get_state_id(state)}(cfg, ev1, ev2);\n")
                wrcpp(f"break;\n")

        wrcpp(f" default : abort();\n ")
        wrcpp("  };\n")
        wrcpp("}\n\n")

        ns = f"{self._namespace}::" if self._namespace else ""

        wrcpp(f"Verdict AtomMonitor{num}::step(unsigned /* num_steps */) {{\n")
        wrcpp(
            f"""
            // No more configurations and we have not accepted.
            // That means we reject.
            if (_cfgs.empty()) {{
              return Verdict::FALSE;
            }}
            
            for (auto& cfg : _cfgs) {{
                // XXX: because we already copy the event (instead of using a pointer
                // -- which we cannot use because of the concurrency), we can store the
                // known event in the configuration and always wait only for the unknown one.
                // Would that be more efficient? (It also means bigger configurations...)
            """
        )
        if t1:
            wrcpp(
                f"""
                    Event ev1;
                    auto ev1ty = t1->get(cfg.p1, ev1);
                    if (ev1ty == TraceQuery::WAITING) {{
                        _cfgs.push_new(cfg);
                        continue;
                    }}
                """
            )
        else:
            wrcpp("constexpr auto ev1ty = TraceQuery::END;")
        if t2:
            wrcpp(
                f"""
                    Event ev2;
                    auto ev2ty = t2->get(cfg.p2, ev2);
                    if (ev2ty == TraceQuery::WAITING) {{
                        _cfgs.push_new(cfg);
                        continue;
                    }}
                """
            )
        else:
            wrcpp("constexpr auto ev2ty = TraceQuery::END;")
        t1id = "t1->id()" if t1 else '"-"'
        t2id = "t2->id()" if t2 else '"-"'
        wrcpp(
            f"""
                #ifdef DEBUG_PRINTS
                std::cerr << "{ns}Atom {num} [" << {t1id} << ", " << {t2id} << "] @ (" << cfg.state  << ", " << cfg.p1 << ", " << cfg.p2 << "): ";
            """
        )
        if t1:
            wrcpp(
                f"""
                    if (ev1ty == TraceQuery::END) {{
                        std::cerr << "END";
                    }} else {{
                        std::cerr << ev1;
                    }}
                """
            )
        else:
            wrcpp('std::cerr << "-";')
        wrcpp('std::cerr << ", ";\n')
        if t2:
            wrcpp(
                f"""
                    if (ev2ty == TraceQuery::END) {{
                        std::cerr << "END";
                    }} else {{
                        std::cerr << ev2;
                    }}
                """
            )
        else:
            wrcpp('std::cerr << "-";')
        wrcpp(
            f"""
                std::cerr << "\\n";
                #endif /* !DEBUG_PRINTS */
            """
        )
        if t1:
            wrcpp(
                f"""
                    if (ev1ty == TraceQuery::END) {{
                        if (state_is_accepting(cfg.state)) {{
                            return Verdict::TRUE;
                        }}
                    }}
            """
            )
        else:
            assert t2
            wrcpp(
                f"""
                    if (ev2ty == TraceQuery::END) {{
                        if (state_is_accepting(cfg.state)) {{
                            return Verdict::TRUE;
                        }}
                    }}
            """
            )
        ev1 = "ev1ty == TraceQuery::END ? nullptr : &ev1" if t1 else "nullptr"
        ev2 = "ev2ty == TraceQuery::END ? nullptr : &ev2" if t2 else "nullptr"
        wrcpp(f"_step(cfg, {ev1}, {ev2});")
        wrcpp("}\n")

        wrcpp(f"_cfgs.rotate();")
        wrcpp(" return Verdict::UNKNOWN;\n")
        wrcpp("}\n\n")

    def _generate_atom_header(self, atom_formula, automaton, num, wrh):
        ns = self._namespace or ""
        wrh(
            f"""
        #ifndef _ATOM_{num}_H__{ns}
        #define _ATOM_{num}_H__{ns}
        """
        )
        dump_codegen_position(wrh)
        wrh('#include "regular-atom-monitor.h"\n\n')
        if self._namespace:
            wrh(f"namespace {self._namespace} {{\n\n")
        dump_codegen_position(wrh)
        wrh(f"/* {atom_formula}*/\n")
        wrh(f"class AtomMonitor{num} : public RegularAtomMonitor {{\n\n")
        for state in automaton.states():
            dump_codegen_position(wrh)
            wrh(
                f"void stepState_{automaton.get_state_id(state)}(EvaluationState& cfg, const Event *ev1, const Event *ev2);\n"
            )
        wrh(f"void _step(EvaluationState &cfg, const Event *ev1, const Event *ev2);\n")
        wrh("public:\n")
        wrh(f"AtomMonitor{num}(HNLInstance& instance);\n\n")
        wrh(f"Verdict step(unsigned num = 0);\n\n")
        wrh("};\n\n")
        if self._namespace:
            wrh(f"}} // namespace {self._namespace}\n")
        wrh("#endif\n")

    def _generate_atom_with_funs(self, wrcpp, atom_formula: IsPrefix, num):
        lf, rf = (
            atom_formula.children[0].functions(),
            atom_formula.children[1].functions(),
        )
        lf_name, rf_name = lf[0].name if lf else None, rf[0].name if rf else None
        lfarg = f", Function *lf /* {lf_name} */" if lf else ""
        rfarg = f", Function *rf /* {rf_name} */" if rf else ""

        wrcpp(f'#include "atom-{num}.h"\n\n')
        if lf_name:
            wrcpp(f'#include "function-{lf_name}.h"\n')
        if rf_name:
            wrcpp(f'#include "function-{rf_name}.h"\n')

        if self._namespace:
            wrcpp(f"using namespace {self._namespace};\n\n")
        dump_codegen_position(wrcpp)
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(HNLInstance& instance{lfarg}{rfarg}) \n  : FunctionAtomMonitor(ATOM_{num}), "
        )
        monitor_init = []
        if lf:
            args = ", ".join(f"instance.{t.name}" for t in lf[0].traces)
            monitor_init.append(
                f"static_cast<Function_{lf_name}*>(lf)->getTraceSet({args})"
            )
        else:
            # dummy argument that says the trace set is the one on the right
            tr = atom_formula.children[0].trace_variables()
            assert len(tr) == 1, atom_formula.children[0]
            monitor_init.append(f"instance.{tr[0].name}")

        if rf:
            args = ", ".join(f"instance.{t.name}" for t in rf[0].traces)
            monitor_init.append(
                f"static_cast<Function_{rf_name}*>(rf)->getTraceSet({args})"
            )
        else:
            # dummy argument that says the trace set is the one on the right
            tr = atom_formula.children[1].trace_variables()
            assert len(tr) == 1, atom_formula.children[1]
            monitor_init.append(f"instance.{tr[0].name}")

        wrcpp(f"monitor({', '.join(monitor_init)})")
        wrcpp("{}\n\n")

        wrcpp(f"Verdict AtomMonitor{num}::step(unsigned /* num_steps */) {{ \n")
        wrcpp(
            """
        auto verdict = monitor.step();
        switch (verdict) {
          case Verdict::FALSE: return Verdict::TRUE;
          case Verdict::TRUE:  return Verdict::FALSE;
          default:             return Verdict::UNKNOWN;
        };
        """
        )
        wrcpp("}")

    def _generate_atom_with_funs_header(self, atom_formula, num, wrh):
        ns = self._namespace or ""
        wrh(
            f"""
        #ifndef _ATOM_{num}_H__{ns}
        #define _ATOM_{num}_H__{ns}
        """
        )
        dump_codegen_position(wrh)
        wrh('#include "function-atom-monitor.h"\n\n')
        wrh(f'#include "{self._submonitors_dirs[num]}/hnl-monitor.h"\n\n')
        if self._namespace:
            wrh(f"namespace {self._namespace} {{\n\n")

        lf, rf = (
            atom_formula.children[0].functions(),
            atom_formula.children[1].functions(),
        )
        lf_name, rf_name = lf[0].name if lf else None, rf[0].name if rf else None
        lf = f", Function * lf/* {lf_name} */" if lf else ""
        rf = f", Function * rf/* {rf_name} */" if rf else ""

        dump_codegen_position(wrh)
        wrh(f"/* {atom_formula}*/\n")
        wrh(f"class AtomMonitor{num} : public FunctionAtomMonitor {{\n\n")
        wrh(f"  atom{num}::FunctionHNLMonitor monitor;\n")
        wrh("public:\n")
        wrh(f"AtomMonitor{num}(HNLInstance& instance{lf}{rf});\n\n")
        wrh(f"Verdict step(unsigned num = 0);\n\n")
        wrh("};\n\n")
        if self._namespace:
            wrh(f"}} // namespace {self._namespace}\n")
        wrh("#endif\n")

    def gen_handle_state(self, aut_num, atom_formula, automaton, priorities, wrcpp):

        lvar = atom_formula.children[0].program_variables()
        rvar = atom_formula.children[1].program_variables()
        assert len(lvar) <= 1, lvar
        assert len(rvar) <= 1, rvar
        lvar = lvar[0].name if lvar else None
        rvar = rvar[0].name if rvar else None
        if not (lvar or rvar):
            raise NotImplementedError("This case is unsupported yet")
        if not lvar:
            raise NotImplementedError("This case is unsupported yet")

        for state in automaton.states():
            transitions = [t for t in automaton.transitions() if t.source == state]
            dump_codegen_position(wrcpp)
            wrcpp(
                f"void AtomMonitor{aut_num}::stepState_{automaton.get_state_id(state)}(EvaluationState& cfg, const Event *ev1, const Event *ev2) {{\n"
            )

            wrcpp(" bool matched = false;\n")
            for prio in priorities:
                wrcpp(f"/* --------------- priority {prio} --------------- */\n")
                ptransitions = [t for t in transitions if t.priority == prio]
                if not ptransitions:
                    continue
                ### Handle epsilon steps
                self.handle_epsilon_steps(automaton, lvar, ptransitions, rvar, wrcpp)

                ### Handle left-epsilon steps
                self.handle_left_epsilon_steps(
                    automaton, lvar, ptransitions, rvar, wrcpp
                )

                ### Handle right-epsilon steps
                self.handle_right_epsilon_steps(
                    automaton, lvar, ptransitions, rvar, wrcpp
                )

                ### Handle letters
                self.handle_letters(automaton, lvar, ptransitions, rvar, wrcpp)

                dump_codegen_position(wrcpp)
                wrcpp("if (matched) { return; }")
                if prio > 0:
                    # if this was not the least priority, continue with the next priority transitions
                    wrcpp(
                        "else {\n"
                        "#ifdef DEBUG_PRINTS\n"
                        f'std::cerr << "    => no transition in priority {prio} matched\\n";\n'
                        "#endif /* !DEBUG_PRINTS */\n"
                        "}"
                    )
                else:
                    # otherwise the matching failed
                    wrcpp(
                        "else {  \n"
                        "     #ifdef DEBUG_PRINTS\n"
                        f'    std::cerr << "    => no transition matched\\n";\n'
                        "     #endif /* !DEBUG_PRINTS */\n"
                        "     /* this was the least priority, drop the cfg */\n"
                        "     return;"
                        "}\n\n"
                    )
            wrcpp("}\n\n ")

    def handle_letters(self, automaton, lvar, ptransitions, rvar, wrcpp):
        tmp = [
            t
            for t in ptransitions
            if not t.label[0].is_epsilon() and not t.label[1].is_epsilon()
        ]
        if not tmp:
            return

        dump_codegen_position(wrcpp)
        wrcpp(f" if (ev1 && ev2) {{\n ")
        for t in tmp:
            wrcpp(
                f" /* {t} */\n "
                "#ifdef DEBUG_PRINTS\n"
                f' std::cerr << "  -- {lvar} = {t.label[0]}; {rvar} = {t.label[1]} -->\\n";\n'
                "#endif /* !DEBUG_PRINTS */\n"
            )
            wrcpp(
                f" if (ev1->{lvar} == {t.label[0]} && ev2->{rvar} == {t.label[1]}) {{\n"
            )
            wrcpp(
                f"   matched = true;\n "
                f"  _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1 + 1, cfg.p2 + 1);\n "
            )
            wrcpp(
                "#ifdef DEBUG_PRINTS\n"
                f'   std::cerr << "    => new (" <<_cfgs.back_new().state  << ", " << _cfgs.back_new().p1 << ", " << _cfgs.back_new().p2 << ")\\n";\n'
                "#endif /* !DEBUG_PRINTS */\n"
            )
            wrcpp("}\n")
        wrcpp("}\n")

    def handle_right_epsilon_steps(self, automaton, lvar, ptransitions, rvar, wrcpp):
        tmp = [
            t
            for t in ptransitions
            if not t.label[0].is_epsilon() and t.label[1].is_epsilon()
        ]
        if not tmp:
            return

        dump_codegen_position(wrcpp)
        wrcpp(f" if (ev1 != nullptr) {{\n")
        for t in tmp:
            wrcpp(
                f" /* {t} */\n "
                "#ifdef DEBUG_PRINTS\n"
                f' std::cerr << "  -- {lvar} = {t.label[0]}; {rvar} = {t.label[1]} -->\\n";\n'
                "#endif /* !DEBUG_PRINTS */\n"
            )
            wrcpp(f" if (ev1->{lvar} == {t.label[0]}) {{\n")
            wrcpp(
                f"   matched = true;\n "
                f"  _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1 + 1, cfg.p2);\n "
            )
            wrcpp(
                "#ifdef DEBUG_PRINTS\n"
                f'   std::cerr << "    => new (" <<_cfgs.back_new().state  << ", " << _cfgs.back_new().p1 << ", " << _cfgs.back_new().p2 << ")\\n";\n'
                "#endif /* !DEBUG_PRINTS */\n"
            )
            wrcpp("}\n")
        wrcpp("}\n")

    def handle_left_epsilon_steps(self, automaton, lvar, ptransitions, rvar, wrcpp):
        tmp = [
            t
            for t in ptransitions
            if t.label[0].is_epsilon() and not t.label[1].is_epsilon()
        ]
        if not tmp:
            return

        dump_codegen_position(wrcpp)
        wrcpp(f" if (ev2 != nullptr) {{\n")
        for t in tmp:
            wrcpp(
                f" /* {t} */\n "
                "#ifdef DEBUG_PRINTS\n"
                f' std::cerr << "  -- {lvar} = {t.label[0]}; {rvar} = {t.label[1]} -->\\n";\n'
                "#endif /* !DEBUG_PRINTS */\n"
            )
            wrcpp(f" if (ev2->{rvar} == {t.label[1]}) {{\n")
            wrcpp(
                f"   matched = true;\n "
                f"   _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1, cfg.p2 + 1);\n "
            )
            wrcpp(
                "#ifdef DEBUG_PRINTS\n"
                f'   std::cerr << "    => new (" << _cfgs.back_new().state  << ", " <<  _cfgs.back_new().p1 << ", " <<  _cfgs.back_new().p2 << ")\\n";\n'
                "#endif /* !DEBUG_PRINTS */\n"
            )
            wrcpp("}\n")
        wrcpp("}\n")

    def handle_epsilon_steps(self, automaton, lvar, ptransitions, rvar, wrcpp):
        for t in (
            t
            for t in ptransitions
            if t.label[0].is_epsilon() and t.label[1].is_epsilon()
        ):
            wrcpp(
                f" /* {t} */\n "
                "#ifdef DEBUG_PRINTS\n"
                f' std::cerr << "  -- {lvar} = {t.label[0]}; {rvar} = {t.label[1]} -->\\n";\n'
                "#endif /* !DEBUG_PRINTS */\n"
            )
            dump_codegen_position(wrcpp)
            wrcpp(f"   matched = true;\n ")
            wrcpp(
                f"   _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1, cfg.p2);\n "
            )
            wrcpp(
                "#ifdef DEBUG_PRINTS\n"
                f'   std::cerr << "    => new (" << _cfgs.back_new().state  << ", " <<  _cfgs.back_new().p1 << ", " <<  _cfgs.back_new().p2 << ")\\n";\n'
                "#endif /* !DEBUG_PRINTS */\n"
            )

    def _aut_to_html(self, filename, A):
        """
        Dump automaton into HTML + JS page, an alternative to graphviz
        that should handle the graphs more nicely.
        """
        assert filename.endswith(".html"), filename
        with self.new_dbg_file(filename) as f:
            self.input_file(f, "../../partials/html/graph-view-start.html")
            f.write("elements: ")
            A.to_json(f)
            f.write(",")
            self.input_file(f, "../../partials/html/graph-view-end.html")

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

    def generate_tests(self, alphabet):
        print("-- Generating tests --")
        makedirs(f"{self.out_dir}/tests", exist_ok=True)

        self.gen_config(
            "CMakeLists-tests.txt.in",
            "tests/CMakeLists.txt",
            {
                "@submonitors_libs@": " ".join(self._submonitors),
            },
        )

        for F, tmp in self._formula_to_automaton.items():
            num, A = tmp
            for test_num in range(0, 20):
                if test_num < 10:
                    # make sure to generate some short tests
                    path_len = random.randrange(0, 5)
                else:
                    path_len = random.randrange(5, 100)

                path = random_path(A, path_len)
                self.gen_test(A, F, num, path, test_num)

    def gen_test(self, A, F, num, path, test_num):
        assert A.is_initial(path[0].source), "Path starts with non-initial state"
        is_accepting = path_is_accepting(A, path)
        lvar = F.children[0].program_variables()
        rvar = F.children[1].program_variables()
        assert len(lvar) <= 1, lvar
        assert len(rvar) <= 1, rvar
        if not (lvar or rvar):
            raise NotImplementedError("This case is unsupported yet")
        if not lvar:
            raise NotImplementedError("This case is unsupported yet")
        vars = (lvar[0].name if lvar else None, rvar[0].name if rvar else None)
        with self.new_file(f"tests/test-trace-{num}-{test_num}.cpp") as f:
            wr = f.write
            dump_codegen_position(f)
            wr(f"// The path used to generate this test:\n\n")
            for t in path:
                wr(f"// {t}\n")
            wr(f"// Accepting: {is_accepting}\n\n")
            dump_codegen_position(f)
            wr("Trace *trace1 = new Trace{1};\n")
            wr("Trace *trace2 = new Trace{2};\n\n")
            for i in range(0, 2):
                n = 0
                for t in path:
                    if t.label[i].is_epsilon():
                        continue
                    wr(f"trace{i+1}->append(Event{{ .{vars[i]} = {t.label[i]}}});\n")
                    n += 1
                wr(f"trace{i+1}->setFinished();")
                wr(f"/* Trace {i + 1} length: {n} */\n\n")

        self.gen_file(
            "test-atom.cpp.in",
            f"tests/test-atom-{num}-{test_num}.cpp",
            {
                "@TRACE@": f'#include "test-trace-{num}-{test_num}.cpp"',
                "@TRACE_VARIABLES@": ", ".join(
                    (f"trace{i+1}" for i, v in enumerate(vars) if v is not None)
                ),
                "@ATOM_NUM@": str(num),
                "@FORMULA@": str(F),
                "@MAX_TRACE_LEN@": str(len(path)),
                "@EXPECTED_VERDICT@": (
                    "Verdict::TRUE" if is_accepting else "Verdict::FALSE"
                ),
                "@namespace_using@": (
                    f"using namespace {self._namespace};" if self._namespace else ""
                ),
            },
        )

    def _gen_function_files(self, fun: Function):
        with self.new_file(f"function-{fun.name}.h") as f:
            wr = f.write
            ns = self._namespace or ""
            wr(
                f"""
            #ifndef _FUNCTION_{fun.name}_H__{ns}
            #define _FUNCTION_{fun.name}_H__{ns}
            """
            )

            wr('#include "function.h"\n')
            wr('#include "sharedtraceset.h"\n\n')

            wr(f"class Function_{fun.name} : public Function{{\n")

            wr("public:\n")
            wr(" virtual SharedTraceSet& getTraceSet(")
            wr(", ".join((f"Trace *{tr.name}" for tr in fun.traces)))
            wr(") = 0;\n")
            wr("};\n")
            wr("#endif\n")

    def generate_functions(self, formula, embedding_data={"monitor_name": ""}):
        with self.new_file("functions.h") as f:
            dump_codegen_position(f)
            f.write(f'#ifndef HNL_FUNCTIONS__{embedding_data["monitor_name"]}\n')
            f.write(f'#define HNL_FUNCTIONS__{embedding_data["monitor_name"]}\n')
            f.write("#include <memory>\n")
            f.write('#include "function.h"\n\n')
            for fun in formula.functions():
                f.write(
                    f"std::unique_ptr<Function> createFunction_{fun.name}(CmdArgs *cmd);\n"
                )
            f.write(f'#endif // !HNL_FUNCTIONS__{embedding_data["monitor_name"]}\n')

        with self.new_file("functions-initialize.h") as f:
            dump_codegen_position(f)
            for fun in formula.functions():
                f.write(f"function_{fun.name} = createFunction_{fun.name}(_cmd);\n")

        with self.new_file("function-instances.h") as f:
            dump_codegen_position(f)
            for fun in formula.functions():
                f.write(f"std::unique_ptr<Function> function_{fun.name};\n")

        for fun in formula.functions():
            self._gen_function_files(fun)

        with self.new_file("gen-function-traces.h") as f:
            dump_codegen_position(f)
            for fun in formula.functions():
                f.write(f"function_{fun.name}->step();\n")
            f.write("if (finished) {")
            f.write(" // check if also the function traces generators finished\n")
            for fun in formula.functions():
                f.write(f"finished &= function_{fun.name}->noFutureUpdates();\n")
            f.write("}")

        self.gen_file(
            "function-atom-monitor.h.in",
            "function-atom-monitor.h",
            {
                "@MONITOR_NAME@": embedding_data["monitor_name"],
                "@namespace@": self._namespace or "",
                "@namespace_start@": (
                    f"namespace {self._namespace} {{" if self._namespace else ""
                ),
                "@namespace_end@": (
                    f"}} // namespace {self._namespace}" if self._namespace else ""
                ),
            },
        )

    def generate(self, formula):
        """
        The top-level function to generate code
        """

        if formula.functions():
            self._have_functions = True

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

        assert alphabet, "The alphabet is empty"

        self.generate_monitor(formula, alphabet)

        self.generate_functions(formula)

        self.generate_tests(alphabet)

        self.gen_file(
            "main.cpp.in",
            "main.cpp",
            {
                "@namespace_using@": (
                    f"using namespace {self._namespace};" if self._namespace else ""
                )
            },
        )

        self._copy_common_files()
        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake()

        self.format_generated_code()

    def generate_embedded(self, formula, alphabet, embedding_data: dict):
        """
        The top-level function to generate code
        """

        self.generate_functions(formula, embedding_data)

        self.generate_monitor(formula, alphabet, embedding_data)

        if embedding_data.get("tests"):
            self.generate_tests(alphabet)

        self.gen_file(
            "main.cpp.in",
            "main.cpp",
            {
                "@namespace_using@": (
                    f"using namespace {self._namespace};" if self._namespace else ""
                )
            },
        )

        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake(
            overwrite_keys={"@MONITOR_NAME@": f'"{embedding_data["monitor_name"]}"'},
            embedded=True,
        )
        self.format_generated_code()

    def format_generated_code(self):
        # format the files if we have clang-format
        # FIXME: check clang-format properly instead of catching the exception
        try:
            for path in listdir(self.out_dir):
                if path.endswith(".h") or path.endswith(".cpp"):
                    run(["clang-format", "-i", f"{self.out_dir}/{path}"])
        except FileNotFoundError:
            pass

    def generate_monitor(self, formula, alphabet, embedding_data=None):
        if embedding_data:
            values = {
                "@MONITOR_NAME@": embedding_data["monitor_name"],
                "@namespace@": self._namespace or "",
                "@namespace_start@": (
                    f"namespace {self._namespace} {{" if self._namespace else ""
                ),
                "@namespace_end@": (
                    f"}} // namespace {self._namespace}" if self._namespace else ""
                ),
            }
        else:
            embedding_data = {}
            values = {
                "@MONITOR_NAME@": "",
                "@namespace@": self._namespace or "",
                "@namespace_start@": "",
                "@namespace_end@": "",
            }

        self.gen_file("hnl-monitor.h.in", "hnl-monitor.h", values)
        self.gen_file("hnl-monitor.cpp.in", "hnl-monitor.cpp", values)
        self.gen_file("atom-monitor.h.in", "atom-monitor.h", values)
        self.gen_file("regular-atom-monitor.h.in", "regular-atom-monitor.h", values)

        def gen_automaton(F):
            if not isinstance(F, IsPrefix):
                return
            self.generate_atomic_comparison_automaton(F, alphabet)

        formula.visit(gen_automaton)
        self._generate_monitor(formula, alphabet, embedding_data)
