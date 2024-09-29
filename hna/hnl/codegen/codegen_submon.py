import random
from os import readlink, listdir, makedirs
from os.path import abspath, dirname, islink, join as pathjoin, basename
from subprocess import run
from sys import stderr

from pyeda.inter import bddvar

from hna.automata.automaton import Automaton
from hna.codegen_common.utils import dump_codegen_position, FIXME
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
from .codegen_atomsmon import CodeGenCpp as CodeGenCppAtomsMon, traces_positions


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
        super().__init__(name, args, ctx, out_dir, namespace)

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_dir, "templates/")

        assert (
            self.args.csv_header
        ), "Give --csv-header, other methods not supported yet"
        self._event = [
            [s.strip() for s in event.split(":")]
            for event in self.args.csv_header.split(",")
        ]

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
            "@additional_cflags@": " ".join((d for d in self.args.cflags)),
            "@CMAKE_BUILD_TYPE@": build_type,
            "@monitor_name@": self.name(),
            "@add_submonitors@": "\n".join(
                (
                    f"add_subdirectory({submon_dir})"
                    for submon_dir in (d["out_dir"] for d in self._submonitors)
                )
            ),
            "@submonitors_libs@": " ".join((d["name"] for d in self._submonitors)),
        }
        if overwrite_keys:
            values.update(overwrite_keys)

        if embedded:
            cmakelists = "CMakeLists-sub-embedded.txt.in"
        else:
            cmakelists = "CMakeLists-sub.txt.in"
        self.gen_config(cmakelists, "CMakeLists.txt", values)

    def _generate_hnlinstances(self, formula):
        with self.new_file("instance.h") as f:
            wr = f.write
            ns = self._namespace or ""
            wr(
                f"""
            #ifndef _HNL_INSTANCE_H__{ns}
            #define _HNL_INSTANCE_H__{ns}
            """
            )
            wr("#include <cassert>\n\n")
            wr('#include "trace.h"\n\n')
            wr("class Monitor;\n\n")
            if self._namespace:
                wr(f"namespace {self._namespace} {{\n\n")
            dump_codegen_position(wr)
            wr("struct Instance {\n")
            wr("  /* traces */\n")
            for q in formula.quantifier_prefix:
                wr(f"  Trace *{q.var};\n")
            wr("  /* The monitor this configuration waits for */\n")
            wr("  Monitor *monitor{nullptr};\n\n")
            wr(f"  Instance(")
            for n, q in enumerate(formula.quantifier_prefix):
                if n > 0:
                    wr(", ")
                wr(f"Trace *{q.var}")
            wr(")\n  : ")
            for n, q in enumerate(formula.quantifier_prefix):
                if n > 0:
                    wr(", ")
                wr(f"{q.var}({q.var})")
            wr("{}\n\n")

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
           auto *instance = new Instance{t1, t2};
           ++stats.num_instances;

           #ifdef DEBUG_PRINTS
           std::cerr << "Instance[init"
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
                  auto *instance = new Instance{t2, t1};
                  ++stats.num_instances;

                  #ifdef DEBUG_PRINTS
                    std::cerr << "Instance[init"
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
            # compute the condition to avoid repeating the combinations of traces
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
            wr("\n  auto *instance = new Instance{")
            for n, i in enumerate(traces_positions(t1_pos, N)):
                if n > 0:
                    wr(", ")
                wr(f"t{i}, ")
            wr("};\n")
            wr("++stats.num_instances;\n\n")
            dump_codegen_position(wr)
            ns = f"{self._namespace}::" if self._namespace else ""
            wr("#ifdef DEBUG_PRINTS\n")
            wr(f'std::cerr << "{ns}Instance[init"')
            for i in traces_positions(t1_pos, N):
                wr(f' << ", " << t{i}->id()')
            wr('<< "]\\n";\n')
            wr("#endif /* !DEBUG_PRINTS */\n")
            wr("}\n")
        for i in range(2, len(formula.quantifier_prefix) + 1):
            wr("}\n")

    def _generate_monitor(self, formula):
        """
        Generate a monitor that actually monitors the body of the formula,
        i.e., it creates and moves with atom monitors.
        """
        self._generate_hnlinstances(formula)
        self._generate_create_instances(formula)

    def generate(self, formula):
        """
        The top-level function to generate code
        """
        top_formula, sub_formula = _split_formula(formula)

        # generate this monitor
        self.generate_monitor(top_formula)
        self.generate_submonitors(sub_formula)

        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake()

        self.format_generated_code()

    def generate_embedded(self, formula, gen_main=False, gen_tests=True):
        """
        The top-level function to generate code as an embedded CMake project
        """
        top_formula, sub_formula = _split_formula(formula)

        self.generate_monitor(top_formula)
        self.generate_submonitors(sub_formula)

        # if gen_tests:
        #    self.generate_tests(self.args.alphabet)

        if gen_main:
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
            # overwrite_keys={"@monitor_name@": f'"{embedding_data["monitor_name"]}"'},
            embedded=True,
        )

        self.format_generated_code()

    def generate_submonitors(self, sub_formula):
        nested_out_dir = f"{self.out_dir}/submonitor"
        has_submonitors = sub_formula.has_quantifier_alternation()

        if has_submonitors:
            nested_cg = CodeGenCpp(
                self.sub_name(),
                self.args,
                self.ctx,
                nested_out_dir,
                self.sub_namespace(),
            )
        else:
            nested_cg = CodeGenCppAtomsMon(
                self.sub_name(),
                self.args,
                self.ctx,
                nested_out_dir,
                self.sub_namespace(),
            )
        nested_cg.generate_embedded(sub_formula)
        self._submonitors = [{"name": self.sub_name(), "out_dir": nested_out_dir}]

    def generate_monitor(self, formula):
        values = {
            "@monitor_name@": self.name(),
            "@namespace@": self.namespace(),
            "@sub-namespace@": self.sub_namespace(),
            "@namespace_start@": (
                f"namespace {self._namespace} {{" if self._namespace else ""
            ),
            "@namespace_end@": (
                f"}} // namespace {self._namespace}" if self._namespace else ""
            ),
        }

        self.gen_file("hnl-sub-monitor.h.in", "hnl-monitor.h", values)
        self.gen_file("hnl-sub-monitor.cpp.in", "hnl-monitor.cpp", values)

        self._generate_monitor(formula)
