import random
from os import readlink, listdir, makedirs
from os.path import abspath, dirname, islink, join as pathjoin, basename
from subprocess import run
from sys import stderr

from pyeda.inter import bddvar

from hna.automata.automaton import Automaton
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
    TraceVariable,
    PrenexFormula,
)
from hna.hnl.formula2automata import (
    formula_to_automaton,
    compose_automata,
    to_priority_automaton,
)
from hna.codegen_common.codegen import CodeGen
from .codegen_atomsmon import CodeGenCpp as CodeGenCppAtomsMon


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

    def __init__(self, args, ctx, out_dir: str = None, namespace: str = None):
        super().__init__(args, ctx, out_dir)

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_dir, "templates/")
        self._namespace = namespace
        self._automata = {}
        self._add_gen_files = []
        self._submonitors_dirs = {}
        self._submonitors = []

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
            assert not has_submonitors, "Not handled yet"
            cmakelists = "CMakeLists-embedded.txt.in"
        elif has_submonitors:
            cmakelists = "CMakeLists-sub.txt.in"
        else:
            cmakelists = "CMakeLists.txt.in"
        self.gen_config(cmakelists, "CMakeLists.txt", values)

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

    def _generate_create_instances_nested_mon(self, embedding_data):
        is_nested_monitor = embedding_data.get("is_nested_monitor") is not None
        ns = f"{self._namespace}::" if self._namespace else ""

        with self.new_file("create-instances-left.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            if is_nested_monitor:
                wr("/* the code that precedes this defines a variable `tl` */\n\n")
                wr(
                    f"""
                for (auto &[tr_id, tr] : _traces_r) {{
                    auto *instance = new HNLInstance{{tl, tr, INITIAL_ATOM}};
                    ++stats.num_instances;
                    
                    instance->monitor = createAtomMonitor(INITIAL_ATOM, *instance);
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
            if is_nested_monitor:
                wr("/* the code that precedes this defines a variable `tr` */\n\n")
                wr(
                    f"""
                for (auto &[tl_id, tl] : _traces_l) {{
                    auto *instance = new HNLInstance{{tl, tr, INITIAL_ATOM}};
                    ++stats.num_instances;

                    instance->monitor = createAtomMonitor(INITIAL_ATOM, *instance);
                        
                    #ifdef DEBUG_PRINTS
                    std::cerr << "{ns}HNLInstance[init" << ", " << tl->id() << ", " << tr->id() << "]\\n";
                    #endif /* !DEBUG_PRINTS */
                }}
                """
                )

            else:
                wr("(void)tr; abort(); /* this function should be never called */\n")

    def _generate_monitor(self, formula, alphabet, embedding_data):
        """
        Generate a monitor that actually monitors the body of the formula,
        i.e., it creates and moves with atom monitors.
        """
        self._generate_hnlinstances(formula)
        self._generate_create_instances(formula)
        # self._generate_create_instances_nested_mon(embedding_data)

    def generate_toplevel_monitor(self, formula, alphabet, embedding_data):
        """
        Generate a monitor that moves with nested HNL monitors.
        """
        self._generate_hnlinstances(formula)
        self._generate_create_instances(formula)

    def generate_submonitor(self, alphabet, formula):
        nested_mon = CodeGenCpp(
            self.args,
            ctx=None,
            out_dir=f"{self.out_dir}/nested-monitor",
            namespace=f"{self._namespace}-nested" if self._namespace else "nested",
        )

        embedding_data = {
            "monitor_name": f"nested",
            "tests": True,
            "is_nested_monitor": True,
        }

        nested_mon.generate_embedded(formula, alphabet, embedding_data)

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

    def generate(self, formula):
        """
        The top-level function to generate code
        """

        alphabet = self.args.alphabet

        top_formula, sub_formula = _split_formula(formula)
        has_submonitors = bool(sub_formula)

        has_submonitors = self.generate_monitor(formula, alphabet)

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
        raise NotImplementedError("We must add to the already generated CMake")
        self.generate_cmake(has_submonitors=has_submonitors)

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
        self.gen_file("hnl-sub-monitor.h.in", "hnl-sub-monitor.h", values)
        self.gen_file("hnl-sub-monitor.cpp.in", "hnl-sub-monitor.cpp", values)

        self.generate_toplevel_monitor(top_formula, alphabet, embedding_data)
        self.generate_submonitor(alphabet, sub_formula)
