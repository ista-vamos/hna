from itertools import chain
from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin, basename

from hna.codegen_common.utils import dump_codegen_position
from hna.hnl.formula import (
    ForAllFromFun,
    Exists,
)
from hna.codegen_common.codegen import CodeGen
from .codegen_atomsmon import CodeGenCpp as CodeGenCppAtomsMon
from .utils import _split_formula


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
            wr("  sub::HNLMonitor *monitor{nullptr};\n\n")
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
            # wr(", monitor(new sub::HNLMonitor()")
            wr("{}\n\n")

            wr("};\n\n")

            wr(self.namespace_end())
            wr("\n\n")

            wr("#endif\n")

    def _generate_create_instances(self, formula):
        _, _, q2set = self.input_tracesets(formula)

        with self.new_file("create-instances.h") as f:
            wr = f.write
            dump_codegen_position(wr)
            # XXX: here we might check the same traceset for a new trace
            # multiple times, but we do not care that much
            checked = set()
            for n, quantifier in enumerate(formula.quantifier_prefix):
                traceset = q2set[quantifier]
                if traceset in checked:
                    continue
                checked.add(traceset)

                dump_codegen_position(wr)
                if traceset is None:
                    wr(f"if (auto *t_new = traces.getNewTrace()) {{\n")
                else:
                    wr(
                        f"if (auto *t_new = traces_{traceset.c_name()}.getNewTrace()) {{\n"
                    )

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
                q2set[q] == traceset
            ):  # this quantifier can be instantiated with the new trace
                self._gen_combinations(n, formula, traceset, q2set, new_ns, wr)
                new_ns.append(n)

    def _gen_combinations(self, new_n, formula, traceset, q2set, new_ns, wr):
        dump_codegen_position(wr)
        for n, q in enumerate(formula.quantifier_prefix):
            i = n + 1
            if n == new_n:
                wr(f"  auto *{q.var} = t_new;\n")
            else:
                ts = q2set[q]
                if ts is None:
                    wr(f"for (auto &[t{i}_id, t{i}_ptr] : {ts}) {{\n")
                    wr(f"  auto *{q.var} = t{i}_ptr.get();\n")
            if n in new_ns:
                wr(f"if ({q.var} == t_new) {{ continue; }}\n")

        dump_codegen_position(wr)
        args = ",".join(
            chain(
                (str(q.var) for q in formula.quantifier_prefix),
                (f"/* fixed */ {q.var}" for q in self._fixed_quantifiers or ()),
            )
        )
        wr(f"\n  auto *instance = new Instance({args});\n")
        wr(f"    instance->monitor = new sub::HNLMonitor();\n")
        wr(f"    _instances.emplace_back(instance);\n")
        wr("++stats.num_instances;\n\n")

        ns = f"{self._namespace}::" if self._namespace else ""
        wr("#ifdef DEBUG_PRINTS\n")
        wr(f'std::cerr << "{ns}Instance["')
        wr('<< "]\\n";\n')
        wr("#endif /* !DEBUG_PRINTS */\n")

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
                    q.fun.name != "traces"
                ), "Collision in the name of obervations and function"
                set2quantifier.setdefault(q.fun, []).append(q)
                q2setname[q] = q.fun
            else:
                # None means observed traces (better than some string that could collide with the name
                # of the function)
                set2quantifier.setdefault(None, []).append(q)
                q2setname[q] = None

        return (
            [str(q.var) for q in self._fixed_quantifiers or ()],
            set2quantifier,
            q2setname,
        )

    def _traces_attribute_str(self, formula):
        lines = []
        fixed, set2q, q2set = self.input_tracesets(formula)
        # Add attributes for quantifiers fixed by parent monitors
        print(set2q)
        lines = [f"Trace *{q};" for q in (fixed or ())] + [
            f"TraceSetView "
            + ("traces" if traceset is None else f"traces_{traceset.c_name()}")
            + ";"
            for traceset, q in set2q.items()
        ]
        return "\n".join(lines)

    def _traces_ctors_dtors(self, formula):
        decls = []
        fixed, set2q, q2setname = self.input_tracesets(formula)

        with self.new_file("hnl-monitor-ctors-dtors.h") as f:
            dump_codegen_position(f)
            wr = f.write

            args = [f"Trace *{q}" for q in fixed]
            proto = f"HNLMonitor(const AllTraceSets& TS {',' if args else ''}{', '.join(args)})"
            decls.append(f"{proto};")

            args = [f"{q}({q})" for q in fixed]

            for traceset, qs in set2q.items():
                if traceset is None:
                    args.append(f"traces(TS.traces)")
                else:
                    funargs = ",".join((str(t) for t in traceset.traces))
                    args.append(
                        f"traces_{traceset.c_name()}(TS.{traceset.name}.getTraceSet({funargs}))"
                    )
            wr(f"HNLMonitor::{proto} : TS(TS) {',' if args else ''}")
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
        top_formula, sub_formula, fixed_quantifiers = _split_formula(formula)
        negate_submonitor_result = isinstance(sub_formula.quantifier_prefix[0], Exists)

        # generate this monitor
        self.generate_monitor(top_formula, negate_submonitor_result)
        self.generate_submonitors(sub_formula, fixed_quantifiers)

        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake()

        self.format_generated_code()

    def generate_embedded(self, formula, gen_main=False, gen_tests=True):
        """
        The top-level function to generate code as an embedded CMake project
        """
        top_formula, sub_formula, fixed_quantifiers = _split_formula(formula)
        negate_submonitor_result = isinstance(sub_formula.quantifier_prefix[0], Exists)

        self.generate_monitor(top_formula, negate_submonitor_result)
        self.generate_submonitors(sub_formula, fixed_quantifiers)

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
        has_submonitors = sub_formula.has_different_quantifiers()

        if isinstance(sub_formula.quantifier_prefix[0], Exists):
            sub_formula = sub_formula.negate()

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

    def generate_monitor(self, formula, negate_submonitor_result=False):
        input_traces = self._traces_attribute_str(formula)
        # NOTE: this method generates definitions of ctors and dtors into an .h file,
        # and returns a list of declarations of those ctors and dtors
        ctors_dtors = self._traces_ctors_dtors(formula)

        values = {
            "@monitor_name@": self.name(),
            "@namespace@": self.namespace(),
            "@sub-namespace@": self.sub_namespace(),
            "@namespace_start@": self.namespace_start(),
            "@namespace_end@": self.namespace_end(),
            "@input_traces@": input_traces,
            "@ctors_dtors@": "\n".join(ctors_dtors),
            "@process_submonitor_verdict@": (
                "verdict = negate_verdict(verdict);" if negate_submonitor_result else ""
            ),
        }

        self.gen_file("hnl-sub-monitor.h.in", "hnl-monitor.h", values)
        self.gen_file("hnl-sub-monitor.cpp.in", "hnl-monitor.cpp", values)

        self._generate_monitor(formula)
