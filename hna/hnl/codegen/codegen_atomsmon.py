import random
from os import readlink, listdir, makedirs
from os.path import abspath, dirname, islink, join as pathjoin, basename
from subprocess import run
from sys import stderr

from pyeda.inter import bddvar

from hna.automata.automaton import Automaton
from hna.codegen_common.codegen import CodeGen
from hna.codegen_common.utils import dump_codegen_position
from hna.hnl.codegen.bdd import BDDNode
from hna.hnl.formula import (
    IsPrefix,
    And,
    Or,
    Not,
    Constant,
    Function,
    ForAll,
    PrenexFormula,
)
from hna.hnl.formula2automata import (
    formula_to_automaton,
    compose_automata,
    to_priority_automaton,
)


def random_path(A: Automaton, length: int) -> list:
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


def path_is_accepting(A: Automaton, path: list) -> bool:
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
    return max(t.priority for t in automaton.transitions(state).values())


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


def _check_functions(functions):
    funs = {}
    for fun in functions:
        f = funs.get(fun.name)
        if f is None:
            funs[fun.name] = fun
        else:
            if len(f.traces) != len(fun.traces):
                raise RuntimeError(
                    f"Function '{fun.name}' is used multiple time with different number of arguments:\n{fun} and {f}"
                )


def _universal_quantifiers_prefix(formula: PrenexFormula):
    assert isinstance(formula, PrenexFormula), formula

    univ, rest = [], []
    for n, q in enumerate(formula.quantifier_prefix):
        if isinstance(q, ForAll):
            univ.append(q)
        else:
            rest = formula.quantifier_prefix[n:]
            break

    return univ, rest


def _split_formula(formula: PrenexFormula):
    """
    Split the given formula into a universally quantified formula and the sub-formula
    for the nested monitor. E.g., `forall a. exists b: F` gets transformed into
    two formulas: `forall a. !F'` where `F' = forall b: !F`.
    However, the first formula has only a placeholder constant instead of `!F`,
    because we handle that part separately.
    """
    universal, rest = _universal_quantifiers_prefix(formula)
    if not rest:
        # this formula is only universally quantified
        return formula, None

    F1 = PrenexFormula(universal, Not(Constant("subF")))
    F2 = PrenexFormula([q.swap() for q in rest], Not(formula.formula))
    print("Split formula: topF = ", F1)
    print("Split formula: subF = ", F2)

    return F1, F2


class CodeGenCpp(CodeGen):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.
    """

    def __init__(self, name, args, ctx, out_dir: str = None, namespace: str = None):
        super().__init__(args, ctx, out_dir)

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_dir, "templates/")
        self._name = name
        self._namespace = namespace
        self.BDD = None
        self._bdd_nodes = []
        self._bdd_vars_to_nodes = {}
        self._automata = {}
        self._add_gen_files = []
        self._atoms_files = []

        assert (
            self.args.csv_header
        ), "Give --csv-header, other methods not supported yet"
        self._event = [
            [s.strip() for s in event.split(":")]
            for event in self.args.csv_header.split(",")
        ]

    def _copy_files(self):
        # copy files from the CMD line
        for f in self.args.cpp_files:
            self.copy_file(f)

        # copy common templates
        files = [
            "monitor.h",
            "hnl-sub-monitor-base.h",
            "cmd.h",
            "cmd.cpp",
            "stream.h",
            "trace.h",
            "trace.cpp",
            "traceset.h",
            "traceset.cpp",
            "tracesetview.h",
            "tracesetview.cpp",
            "sharedtraceset.h",
            "sharedtraceset.cpp",
            "verdict.h",
            "atom-base.h",
            "atom-evaluation-state.h",
            # XXX: do this only when functions are used
            "function.h",
        ]

        from_dir = self.common_templates_path
        for f in files:
            if f not in self.args.overwrite_file:
                self.copy_file(f, from_dir=from_dir)

    def generate_cmake(
        self, has_submonitors=False, overwrite_keys=None, embedded=False
    ):
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
            "@MONITOR_NAME@": f'"{self._name}"',
            "@ADD_NESTED_MONITORS@": "\n".join(
                (
                    f"add_subdirectory({submon_dir})"
                    for submon_dir in (d["out_dir"] for d in self._submonitors)
                )
            ),
            "@submonitors_libs@": " ".join(self._submonitors),
        }
        if overwrite_keys:
            values.update(overwrite_keys)

        if embedded:
            assert not has_submonitors, "Not handled yet"
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
        self.copy_file("csvreader.h", from_dir=self.common_templates_path)
        self.copy_file("csvreader.cpp", from_dir=self.common_templates_path)
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

        def gen_bdd(F):
            """
            Recursively build BDD from the formula and create the mapping
            between atoms and BDD variables. Each atom represents a variable.
            """
            if isinstance(F, IsPrefix):
                v = bddvar(str(F))
                nd = BDDNode(F, v)
                self._bdd_nodes.append(nd)
                self._bdd_vars_to_nodes[v] = nd
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

        self.BDD = BDD

    def _generate_bdd_code(self, formula):

        def bdd_to_action(bdd):
            if bdd.is_one():
                return "RESULT_TRUE"
            elif bdd.is_zero():
                return "RESULT_FALSE"

            nd = self._bdd_vars_to_nodes[bdd.top]
            return f"ATOM_{nd.get_id()}"

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
            f.write(
                "// FIXME: rename (or create a new enum with atom types that will coincide with this one) \n"
            )
            f.write("enum HNLEvaluationState {\n")
            f.write("  INVALID      =  0,\n")
            f.write("  FINISHED     = -1, // the atom finished \n")
            f.write("  RESULT_TRUE  = -2, // the atom got result TRUE\n")
            f.write("  RESULT_FALSE = -3, // the atom got result FALSE \n")
            for nd in self._bdd_nodes:
                f.write(
                    f"  ATOM_{nd.get_id()} = {nd.get_id()}, // the atom is atom {nd.get_id()} \n"
                )
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
            wbg.add(self.BDD)
            rows = {}
            while wbg:
                bdd = wbg.pop()
                if bdd in seen or bdd.is_one() or bdd.is_zero():
                    continue
                seen.add(bdd)

                hi = bdd.restrict({bdd: 1})
                lo = bdd.restrict({bdd: 0})
                wbg.add(hi)
                wbg.add(lo)

                nd = self._bdd_vars_to_nodes[bdd.top]
                assert nd.get_id() not in rows, rows
                rows[nd.get_id()] = (
                    f"  {{ {bdd_to_action(bdd)}, {bdd_to_action(hi)}, {bdd_to_action(lo)} }} ,\n"
                )

            idxs = sorted(rows)
            for idx in idxs:
                f.write(rows[idx])

            f.write("};\n\n")

            dump_codegen_position(f)
            f.write(
                f"static constexpr HNLEvaluationState INITIAL_ATOM = {bdd_to_action(self.BDD.top)};\n"
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
            wr('#include "atom-identifier.h"\n\n')
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
            wr("state(init_state) { assert(state != INVALID); }\n\n")

            # wr(f"  HNLInstance(const HNLInstance& other, HNLEvaluationState init_state)\n  : ")
            # for q in formula.quantifier_prefix:
            #    wr(f"{q.var}(other.{q.var}), ")
            # wr("state(init_state) { assert(state != INVALID); }\n\n")

            wr("AtomIdentifier createMonitorID(int monitor_type) {")
            wr("switch (monitor_type) {")
            for nd in self._bdd_nodes:
                identifier = f"AtomIdentifier{{ATOM_{nd.get_id()}"
                trace_variables = [t.name for t in nd.formula.trace_variables()]
                for q in formula.quantifiers():
                    if q.var.name in trace_variables:
                        identifier += f", {q.var.name}->id()"
                    else:
                        identifier += ",0"
                identifier += "}"
                wr(f"case ATOM_{nd.get_id()}: return {identifier};\n")
            wr(f"default: abort();\n")
            wr("};\n")
            wr("}\n\n")

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
            wr(
                """
            /* Create the instances

               XXX: Maybe it could be more efficient to just have a hash map
               XXX: and check if we have generated the combination (instead of checking
               XXX: those conditions) */
            """
            )

            if self.args.reduction:
                self._gen_create_instance_reduced(formula, wr)
            else:
                self._gen_create_instance(N, formula, wr)

    def _gen_create_instance_reduced(self, formula, wr):
        if len(formula.quantifier_prefix) > 2:
            raise NotImplementedError(
                "Reductions work now only with at most 2 quantifiers"
            )

        dump_codegen_position(wr)
        wr(
            """
        for (auto &[t2_id, t2_ptr] : _traces) {
            auto *t2 = t2_ptr.get();
        """
        )

        if "reflexive" in self.args.reduction:
            wr("if (t1 == t2) { continue;}")

        wr(
            """
           auto *instance = new HNLInstance{t1, t2, INITIAL_ATOM};
           ++stats.num_instances;

           instance->monitor = createAtomMonitor(INITIAL_ATOM, *instance);

           #ifdef DEBUG_PRINTS
           std::cerr << "HNLInstance[init"
                     << ", " << t1->id() << ", " << t2->id() << "]\\n";
           #endif /* !DEBUG_PRINTS */
        """
        )

        if "symmetric" in self.args.reduction:
            wr("}\n")
        else:
            wr(
                """
               if (t1 != t2)  {
                  auto *instance = new HNLInstance{t2, t1, INITIAL_ATOM};
                  ++stats.num_instances;

                  instance->monitor = createAtomMonitor(INITIAL_ATOM, *instance);
                  #ifdef DEBUG_PRINTS
                    std::cerr << "HNLInstance[init"
                              << ", " << t2->id() << ", " << t1->id() << "]\\n";
                  #endif /* !DEBUG_PRINTS */
               }
            }
            """
            )

    def _gen_create_instance(self, N, formula, wr):
        dump_codegen_position(wr)
        for i in range(2, N + 1):
            wr(f"for (auto &[t{i}_id, t{i}_ptr] : _traces) {{\n")
            wr(f"  auto *t{i} = t{i}_ptr.get();\n")

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
            wr("\n  auto *instance = new HNLInstance{")
            for i in traces_positions(t1_pos, N):
                wr(f"t{i}, ")
            wr("INITIAL_ATOM};\n")
            wr("++stats.num_instances;\n\n")
            wr("instance->monitor = createAtomMonitor(INITIAL_ATOM, *instance);\n")
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

    def _generate_atom_monitor(self):
        with self.new_file("create-atom-monitor.h") as f:
            dump_codegen_position(f)
            f.write("switch(monitor_type) {\n")
            for nd in self._bdd_nodes:
                num, F = nd.get_id(), nd.formula
                lf, rf = F.children[0].functions(), F.children[1].functions()
                lf = f", function_{lf[0].name}.get()" if lf else ""
                rf = f", function_{rf[0].name}.get()" if rf else ""
                f.write(
                    f"case ATOM_{num}: monitor = new AtomMonitor{num}(instance{lf}{rf}); break;\n"
                )
            f.write("default: abort();\n")
            f.write("}\n\n")

    def _generate_monitor(self, formula, alphabet, embedding_data):
        """
        Generate a monitor that actually monitors the body of the formula,
        i.e., it creates and moves with atom monitors.
        """
        self._generate_bdd_code(formula)
        self._generate_hnlinstances(formula)
        self._generate_create_instances(formula)
        # self._generate_create_instances_nested_mon(embedding_data)
        self._generate_automata_code(formula, alphabet)
        self._generate_atom_monitor()

    def generate_toplevel_monitor(self, formula, alphabet, embedding_data):
        """
        Generate a monitor that moves with nested HNL monitors.
        """
        self._generate_hnlinstances(formula)
        self._generate_create_instances(formula)

    def _generate_automata_code(self, formula, alphabet):
        generated_automata = {}
        for nd in self._bdd_nodes:
            print("Generating code for", nd.get_id(), ":", nd.formula)
            assert nd.automaton

            num, F = nd.get_id(), nd.formula
            duplicate_num = generated_automata.get(
                (nd.lvar, nd.rvar, nd.automaton.get_id())
            )
            if duplicate_num is not None:
                with self.new_file(f"atom-{num}.h") as fh, self.new_file(
                    f"atom-{num}.cpp"
                ) as fcpp:
                    self._generate_duplicate_atom(
                        nd, duplicate_num, fh.write, fcpp.write
                    )
                    self._atoms_files.append(f"atom-{num}.cpp")
                continue

            with self.new_file(f"atom-{num}.h") as fh:
                if F.functions():
                    self._generate_atom_with_funs_header(F, num, fh.write)
                else:
                    self._generate_atom_header(F, nd.automaton, num, fh.write)

            with self.new_file(f"atom-{num}.cpp") as fcpp:
                if F.functions():
                    self._generate_atom_with_funs(fcpp.write, formula, F, num)
                else:
                    self._generate_atom(fcpp.write, formula, nd)
            self._atoms_files.append(f"atom-{num}.cpp")
            generated_automata[(nd.lvar, nd.rvar, nd.automaton.get_id())] = num

        with self.new_file("atom-identifier.h") as f:
            ns = self._namespace or ""
            f.write(
                f"""
            #ifndef _ATOM_IDENTIFIER_H__{ns}
            #define _ATOM_IDENTIFIER_H__{ns}

            #include <tuple>
            """
            )
            dump_codegen_position(f)
            if ns:
                f.write(f"namespace {ns} {{\n\n")
            f.write(
                "\n"
                "// An object that can uniquely identify an atom monitor\n"
                "// by its type and ids of the instantiated traces (or 0 if the trace variable"
                "// is not used by the atom).\n"
            )
            f.write("using AtomIdentifier = std::tuple<unsigned")
            f.write(", unsigned" * len(formula.quantifiers()))
            f.write("> ;\n")
            if ns:
                f.write(f"}} // namespace {ns}\n\n")
            f.write("#endif\n")

        with self.new_file("atoms.h") as f:
            ns = self._namespace or ""
            f.write(
                f"""
            #ifndef _ATOMS_H__{ns}
            #define _ATOMS_H__{ns}
            """
            )
            dump_codegen_position(f)
            for nd in self._bdd_nodes:
                f.write(f'#include "atom-{nd.get_id()}.h"\n')
            f.write("#endif\n")

        with self.new_file("do_step.h") as f:
            dump_codegen_position(f)
            f.write("switch (M->type()) {")
            for nd in self._bdd_nodes:
                num = nd.get_id()
                f.write(
                    f"  case {num}: return static_cast<AtomMonitor{num}*>(M)->step();\n"
                )
            f.write(
                f"  case FINISHED: return static_cast<FinishedAtomMonitor*>(M)->step();\n"
            )
            f.write("  default: abort();\n")
            f.write("}")

    def _generate_atom(self, wrcpp, formula, nd):
        atom_formula, num, automaton = nd.formula, nd.get_id(), nd.automaton

        t1 = nd.ltrace.name if nd.ltrace else None
        t2 = nd.rtrace.name if nd.rtrace else None
        if not (t1 or t2):
            raise NotImplementedError("This case is unsupported yet")
        if not t1:
            raise NotImplementedError("This case is unsupported yet")

        wrcpp(f'#include "atom-{num}.h"\n\n')
        if self._namespace:
            wrcpp(f"using namespace {self._namespace};\n\n")
        dump_codegen_position(wrcpp)

        identifier = "AtomIdentifier{st"
        for q in formula.quantifiers():
            if q.var.name in (t1, t2):
                identifier += f",instance.{q.var.name}->id()"
            else:
                identifier += ",0"
        identifier += "}"
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const HNLInstance& instance, HNLEvaluationState st, Trace *lt, Trace *rt) \n  :"
            f" RegularAtomMonitor({identifier}, lt, rt) {{\n\n"
        )
        assert (
            len(automaton.initial_states()) == 1
        ), f"Automaton {num} has multiple initial states"
        wrcpp(
            f"_cfgs.emplace_back({automaton.get_state_id(automaton.initial_states()[0])}, 0, 0);\n"
        )
        wrcpp("}\n\n")

        t1_instance = f"instance.{t1}" if t1 else "nullptr"
        t2_instance = f"instance.{t2}" if t2 else "nullptr"
        identifier = f"AtomIdentifier{{ATOM_{num}"
        for q in formula.quantifiers():
            if q.var.name in (t1, t2):
                identifier += f",instance.{q.var.name}->id()"
            else:
                identifier += ",0"
        identifier += "}"
        dump_codegen_position(wrcpp)
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const HNLInstance& instance) \n  : AtomMonitor{num}(instance, ATOM_{num}, {t1_instance}, {t2_instance}) {{\n\n"
        )
        assert (
            len(automaton.initial_states()) == 1
        ), f"Automaton {num} has multiple initial states"
        wrcpp("}\n\n")

        # create the initial configuration
        priorities = list(set(t.priority for t in automaton.transitions()))
        priorities.sort(reverse=True)

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
            transitions = automaton.transitions(state)
            transitions = list(transitions.values()) if transitions else []
            # assert transitions == [t for t in automaton.transitions() if t.source == state]
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
                std::cerr << "{ns}Atom " << type() << " [" << {t1id} << ", " << {t2id} << "] @ (" << cfg.state  << ", " << cfg.p1 << ", " << cfg.p2 << "): ";
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
        wrh('#include "atom-identifier.h"\n\n')
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
        wrh(f"AtomMonitor{num}(const HNLInstance& instance);\n\n")
        wrh(
            f"AtomMonitor{num}(const HNLInstance& instance, HNLEvaluationState st, Trace *lt, Trace *rt);\n\n"
        )
        wrh(f"Verdict step(unsigned num = 0);\n\n")
        wrh("};\n\n")
        if self._namespace:
            wrh(f"}} // namespace {self._namespace}\n")
        wrh("#endif\n")

    def _generate_duplicate_atom(self, nd, duplicate_of, wrh, wrcpp):
        ns = self._namespace or ""
        num, atom_formula = nd.get_id(), nd.formula

        wrh(
            f"""
        #ifndef _ATOM_{num}_H__{ns}
        #define _ATOM_{num}_H__{ns}
        """
        )
        dump_codegen_position(wrh)
        wrh(f'#include "atom-{duplicate_of}.h"\n\n')
        if self._namespace:
            wrh(f"namespace {self._namespace} {{\n\n")
        dump_codegen_position(wrh)
        wrh(f"/* {atom_formula} */\n\n")
        wrh(
            f"/* This atom is a duplicate of AtomMonitor{duplicate_of} (but possibly trace inputs) */\n"
        )
        wrh(
            f"class AtomMonitor{num} : public AtomMonitor{duplicate_of} {{\n"
            "public:\n"
            f"  AtomMonitor{num}(const HNLInstance&);\n"
            f"}};\n"
        )
        if self._namespace:
            wrh(f"}} // namespace {self._namespace}\n")
        wrh("#endif\n")

        wrcpp(f'#include "atom-{num}.h"\n\n')
        if self._namespace:
            wrcpp(f"using namespace {self._namespace};\n\n")
        dump_codegen_position(wrcpp)
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const HNLInstance& instance) \n  : AtomMonitor{duplicate_of}(instance, ATOM_{num}, instance.{nd.ltrace}, instance.{nd.rtrace}) {{}}\n\n"
        )

    def _generate_atom_with_funs(self, wrcpp, formula, atom_formula: IsPrefix, num):
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
        identifier = f"AtomIdentifier{{ATOM_{num}"
        traces = [t.name for t in atom_formula.trace_variables()]
        for q in formula.quantifiers():
            if q.var.name in traces:
                identifier += f",instance.{q.var.name}->id()"
            else:
                identifier += ",0"
        identifier += "}"

        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const HNLInstance& instance{lfarg}{rfarg}) \n  : FunctionAtomMonitor({identifier}), "
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
        wrh('#include "nested-hnl-atom-monitor.h"\n\n')
        wrh(f'#include "{self._submonitors_dirs[num]}/hnl-atoms-monitor.h.in"\n\n')
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
        wrh(f"AtomMonitor{num}(const HNLInstance& instance{lf}{rf});\n\n")
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
            # transitions = [t for t in automaton.transitions() if t.source == state]
            T = automaton.transitions(state)
            transitions = [t for ts in (T.values() if T else ()) for t in ts]
            dump_codegen_position(wrcpp)
            wrcpp(
                f"void AtomMonitor{aut_num}::stepState_{automaton.get_state_id(state)}(EvaluationState& cfg, const Event *ev1, const Event *ev2) {{\n"
            )

            wrcpp(" bool matched = false;\n")
            grouped_transitions = {}
            # FIXME: use itertools.groupby
            for t in transitions:
                grouped_transitions.setdefault(t.priority, []).append(t)

            for prio in priorities:
                wrcpp(f"/* --------------- priority {prio} --------------- */\n")
                ptransitions = grouped_transitions.get(
                    prio
                )  # [t for t in transitions if t.priority == prio]
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

    def generate_atomic_comparison_automaton(self, bddnode: BDDNode, alphabet):
        assert isinstance(bddnode, BDDNode), bddnode
        assert bddnode.automaton is None

        # we rename both projections to `v(t)` so that when we have another atom
        # that is the same but names of the trace variables, we do not rebuild it
        formula = bddnode.formula
        num = bddnode.get_id()
        nformula = formula.rename_variables("v", "v", "t", "t")
        Ap = self._automata.get(nformula)
        if Ap:
            print(
                f"Duplicate atom for {formula }, re-using the automaton for {nformula}"
            )
            bddnode.automaton = Ap

            if self.args.debug:
                with self.new_dbg_file(f"aut-{num}-prio.dot") as f:
                    Ap.to_dot(f)
            return Ap

        A1 = self._automata.get(nformula.children[0])
        if A1 is None:
            A1 = formula_to_automaton(nformula.children[0], alphabet)
            self._automata[nformula.children[0]] = A1
        else:
            print(f"Hit cache for {nformula.children[0]}")
        A2 = self._automata.get(nformula.children[1])
        if A2 is None:
            A2 = formula_to_automaton(nformula.children[1], alphabet)
            self._automata[nformula.children[1]] = A2
        else:
            print(f"Hit cache for {nformula.children[1]}")

        # NOTE: we do not cache this one
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

        # self._aut_to_html(f"aut-{num}-lhs.html", A1)
        # self._aut_to_html(f"aut-{num}-rhs.html", A2)
        # self._aut_to_html(f"aut-{num}.html", A)
        # self._aut_to_html(f"aut-{num}-prio.html", Ap)

        self._automata[nformula] = Ap

        assert len(Ap.accepting_states()) > 0, f"Automaton has no accepting states"
        assert len(Ap.initial_states()) > 0, f"Automaton has no initial states"

        return Ap

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

        for nd in self._bdd_nodes:
            num = nd.get_id()
            for test_num in range(0, 20):
                if test_num < 10:
                    # make sure to generate some short tests
                    path_len = random.randrange(0, 5)
                else:
                    path_len = random.randrange(5, 100)

                path = random_path(nd.automaton, path_len)
                self.gen_test(nd.automaton, nd.formula, num, path, test_num)

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
        functions_instances = formula.functions()
        functions = list(set(functions_instances))

        # check types of functions
        _check_functions(functions_instances)

        with self.new_file("functions.h") as f:
            dump_codegen_position(f)
            f.write(f'#ifndef HNL_FUNCTIONS__{embedding_data["monitor_name"]}\n')
            f.write(f'#define HNL_FUNCTIONS__{embedding_data["monitor_name"]}\n')
            f.write("#include <memory>\n")
            f.write('#include "function.h"\n\n')
            for fun in functions:
                f.write(
                    f"std::unique_ptr<Function> createFunction_{fun.name}(CmdArgs *cmd);\n"
                )
            f.write(f'#endif // !HNL_FUNCTIONS__{embedding_data["monitor_name"]}\n')

        with self.new_file("functions-initialize.h") as f:
            dump_codegen_position(f)
            for fun in functions:
                f.write(f"function_{fun.name} = createFunction_{fun.name}(_cmd);\n")

        with self.new_file("function-instances.h") as f:
            dump_codegen_position(f)
            for fun in functions:
                f.write(f"std::unique_ptr<Function> function_{fun.name};\n")

        for fun in functions:
            self._gen_function_files(fun)

        with self.new_file("gen-function-traces.h") as f:
            dump_codegen_position(f)
            for fun in functions:
                f.write(f"function_{fun.name}->step();\n")
            f.write("if (finished) {")
            f.write(" // check if also the function traces generators finished\n")
            for fun in functions:
                f.write(f"finished &= function_{fun.name}->noFutureUpdates();\n")
            f.write("}")

    def generate(self, formula, alphabet=None, embedding_data=None):
        """
        The top-level function to generate code
        """

        print(f"Generating (base) monitor for '{formula}' into '{self.out_dir}'")

        alphabet = alphabet or self.args.alphabet

        if embedding_data is not None:
            self._generate_embedded(formula, alphabet, embedding_data)
            return

        self.generate_monitor(formula, alphabet)
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

        self._copy_files()
        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake()

        self.format_generated_code()

    def _get_alphabet(self, formula):
        if not self.args.alphabet:
            print(
                "No alphabet given, using constants from the formula: ",
                formula.constants(),
                file=stderr,
            )
            alphabet = formula.constants()
        else:
            alphabet = [Constant(a) for a in self.args.alphabet]
        assert alphabet, "The alphabet is empty"
        return alphabet

    def _generate_embedded(self, formula, alphabet, embedding_data: dict):
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

    def generate_monitor(self, formula: PrenexFormula, alphabet, embedding_data=None):
        assert not formula.has_quantifier_alternation(), formula

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
        self.gen_file("hnl-sub-monitor.h.in", "hnl-sub-monitor.h", values)
        self.gen_file("hnl-sub-monitor.cpp.in", "hnl-sub-monitor.cpp", values)
        self.gen_file("hnl-atoms-monitor.h.in", "hnl-atoms-monitor.h", values)
        self.gen_file("hnl-atoms-monitor.cpp.in", "hnl-atoms-monitor.cpp", values)
        self.gen_file("atom-monitor.h.in", "atom-monitor.h", values)
        self.gen_file("finished-atom-monitor.h.in", "finished-atom-monitor.h", values)
        self.gen_file("regular-atom-monitor.h.in", "regular-atom-monitor.h", values)

        # there is no sub-formula, this is the monitor for the body of the function
        self._gen_bdd_from_formula(formula)

        for nd in self._bdd_nodes:
            nd.automaton = self.generate_atomic_comparison_automaton(nd, alphabet)

        def gen_automaton(F):
            if not isinstance(F, IsPrefix):
                return

        formula.visit(gen_automaton)

        self._generate_monitor(formula, alphabet, embedding_data)
