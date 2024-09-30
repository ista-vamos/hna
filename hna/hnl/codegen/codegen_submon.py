import random
from itertools import chain
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
    ForAllFromFun,
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
        return formula, None, universal

    F1 = PrenexFormula(universal, Not(Constant("subF")))
    F2 = PrenexFormula([q.swap() for q in rest], Not(formula.formula))
    print("Split formula: topF = ", F1)
    print("Split formula: subF = ", F2)
    print("Universal: ", universal)

    return F1, F2, universal


class CodeGenCpp(CodeGen):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.
    """

    def __init__(
        self,
        name,
        args,
        ctx,
        fixed_quantifiers=None,
        out_dir: str = None,
        namespace: str = None,
    ):
        super().__init__(name, args, ctx, out_dir, namespace)

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_dir, "templates/")
        self._fixed_quantifiers = fixed_quantifiers

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
            wr(
                f"""
            #ifndef HNL_INSTANCE_H__{self.name()}
            #define HNL_INSTANCE_H__{self.name()}
            """
            )
            wr("#include <cassert>\n\n")
            wr('#include "trace.h"\n\n')
            wr('#include "submonitor/hnl-monitor.h"\n\n')

            wr("class Monitor;\n\n")

            wr(self.namespace_start())
            wr("\n\n")

            dump_codegen_position(wr)
            wr("struct Instance {\n")
            wr("  /* variable traces */\n")
            for q in formula.quantifier_prefix:
                wr(f"  Trace *{q.var};\n")
            wr("  /* fixed traces */\n")
            for q in self._fixed_quantifiers or ():
                wr(f"  Trace *{q.var};\n")
            wr("  /* The monitor this configuration waits for */\n")
            wr("  sub::HNLMonitor *monitor;\n\n")
            args = (
                f"Trace *{q.var}"
                for q in chain(formula.quantifier_prefix, self._fixed_quantifiers or ())
            )
            wr(f"  Instance({', '.join(args)})\n  : ")
            wr(
                ", ".join(
                    (
                        f"{q.var}({q.var})"
                        for q in chain(
                            formula.quantifier_prefix, self._fixed_quantifiers or ()
                        )
                    )
                )
            )
            wr(", monitor(new sub::HNLMonitor()")
            wr("){}\n\n")

            wr("};\n\n")

            wr(self.namespace_end())
            wr("\n\n")

            wr("#endif\n")

    def _generate_create_instances(self, formula):
        _, tracesets, q2set = self.input_tracesets(formula)

        with self.new_file("create-instances.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            # XXX: here we might check the same traceset for a new trace
            # multiple times, but we do not care that much
            checked = set()
            for n, quantifier in enumerate(formula.quantifier_prefix):
                traceset = q2set[str(quantifier.var)]
                if traceset in checked:
                    continue
                checked.add(traceset)

                dump_codegen_position(wr)
                wr(f"if (auto *t_new = {traceset}.getNewTrace()) {{\n")

                if self.args.reduction:
                    self._gen_create_instance_reduced(formula, n, wr)
                else:
                    self._gen_create_instance(formula, traceset, q2set, wr)

                wr("}\n\n")

    def _gen_create_instance(self, formula, traceset, q2set, wr):
        dump_codegen_position(wr)

        new_ns = []
        for n, q in enumerate(formula.quantifier_prefix):
            if (
                q2set[str(q.var)] == traceset
            ):  # this quantifier can be instantiated with the new trace
                self._gen_combinations(n, formula, traceset, q2set, new_ns, wr)
                new_ns.append(n)

    def _gen_combinations(self, new_n, formula, traceset, q2set, new_ns, wr):
        dump_codegen_position(wr)
        for n, q in enumerate(formula.quantifier_prefix):
            i = n + 1
            if n == new_n:
                wr(f"  auto *t{i} = t_new;\n")
            else:
                wr(f"for (auto &[t{i}_id, t{i}_ptr] : {q2set[str(q.var)]}) {{\n")
                wr(f"  auto *t{i} = t{i}_ptr.get();\n")
            if n in new_ns:
                wr(f"if (t{n + 1} == t_new) {{ continue; }}\n")

        # there is one less } than quantifiers, because we do not generate
        # for loop for the quantifier to which we assign t_new
        for i in range(1, len(formula.quantifier_prefix)):
            wr("}\n")

    def _gen_create_instance_reduced(self, formula, wr):
        raise NotImplementedError("Not re-implemented after chagnes")
        dump_codegen_position(wr)
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

    def input_tracesets(self, formula):
        """
        Auxiliary (and unified) method to sort quantifiers for code generation
        """
        set2quantifier = {}
        q2setname = {}
        for q in formula.quantifier_prefix:
            if isinstance(q, ForAllFromFun):
                assert (
                    q.fun.c_name() != "traces"
                ), "Collision in the name of obervations and function"
                set2quantifier.setdefault(q.fun.c_name(), []).append(str(q.var))
                q2setname[str(q.var)] = q.fun.c_name()
            else:
                # None means observed traces (better than some string that could collide with the name
                # of the function)
                set2quantifier.setdefault("traces", []).append(str(q.var))
                q2setname[str(q.var)] = "traces"

        return (
            [str(q.var) for q in self._fixed_quantifiers or ()],
            set2quantifier,
            q2setname,
        )

    def _traces_attribute_str(self, formula):
        lines = []
        fixed, tracesets, _ = self.input_tracesets(formula)
        # Add attributes for quantifiers fixed by parent monitors
        for q in fixed or ():
            lines.append(f"Trace *{q};")

        for traceset, quantifiers in tracesets.items():
            lines.append(
                f"TraceSetView {traceset};  // {', '.join(quantifiers)} in {traceset};"
            )
        return "\n".join(lines)

    def _traces_ctors_dtors(self, formula):
        decls = []
        fixed, set2q, _ = self.input_tracesets(formula)

        with self.new_file("hnl-monitor-ctors-dtors.h") as f:
            dump_codegen_position(f)
            wr = f.write

            args = [f"Trace *{q}" for q in fixed]
            args += [f"TraceSetView& {traceset}" for traceset in set2q.keys()]
            proto = f"HNLMonitor({', '.join(args)})"
            decls.append(f"{proto};")

            args = [f"{q}({q})" for q in fixed]
            args += [f"{traceset}({traceset})" for traceset in set2q.keys()]
            wr(f"HNLMonitor::{proto} : ")
            wr(", ".join(args))
            wr("{}\n\n")

        return decls

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
        top_formula, sub_formula, universal_prefix = _split_formula(formula)

        # generate this monitor
        self.generate_monitor(top_formula)
        self.generate_submonitors(sub_formula, universal_prefix)

        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake()

        self.format_generated_code()

    def generate_embedded(self, formula, gen_main=False, gen_tests=True):
        """
        The top-level function to generate code as an embedded CMake project
        """
        top_formula, sub_formula, universal_prefix = _split_formula(formula)

        self.generate_monitor(top_formula)
        self.generate_submonitors(sub_formula, universal_prefix)

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

    def generate_submonitors(self, sub_formula, universal_prefix: list):
        nested_out_dir = f"{self.out_dir}/submonitor"
        has_submonitors = sub_formula.has_quantifier_alternation()

        if has_submonitors:
            nested_cg = CodeGenCpp(
                self.sub_name(),
                self.args,
                self.ctx,
                fixed_quantifiers=(self._fixed_quantifiers or []) + universal_prefix,
                out_dir=nested_out_dir,
                namespace=self.sub_namespace(),
            )
        else:
            nested_cg = CodeGenCppAtomsMon(
                self.sub_name(),
                self.args,
                self.ctx,
                fixed_quantifiers=(self._fixed_quantifiers or []) + universal_prefix,
                out_dir=nested_out_dir,
                namespace=self.sub_namespace(),
            )
        nested_cg.generate_embedded(sub_formula)
        self._submonitors = [{"name": self.sub_name(), "out_dir": nested_out_dir}]

    def generate_monitor(self, formula):
        input_traces = self._traces_attribute_str(formula)
        # NOTE: this method generates definitions of ctors and dtors into an .h file,
        # and returns a list of declarations of those ctors and dtors
        ctors_dtors = self._traces_ctors_dtors(formula)

        ns_start = "\n".join(
            (
                f"namespace {ns} {{"
                for ns in (self._namespace.split("::") if self._namespace else ())
            )
        )
        ns_end = "\n".join(
            (
                f"}} /* namespace {ns} */"
                for ns in (self._namespace.split("::")[::-1] if self._namespace else ())
            )
        )
        values = {
            "@monitor_name@": self.name(),
            "@namespace@": self.namespace(),
            "@sub-namespace@": self.sub_namespace(),
            "@namespace_start@": ns_start,
            "@namespace_end@": ns_end,
            "@input_traces@": input_traces,
            "@ctors_dtors@": "\n".join(ctors_dtors),
        }

        self.gen_file("hnl-sub-monitor.h.in", "hnl-monitor.h", values)
        self.gen_file("hnl-sub-monitor.cpp.in", "hnl-monitor.cpp", values)

        self._generate_monitor(formula)
