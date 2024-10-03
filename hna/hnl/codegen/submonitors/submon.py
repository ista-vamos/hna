from itertools import chain
from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin, basename

from hna.codegen_common.utils import dump_codegen_position
from hna.hnl.formula import (
    ForAllFromFun,
    Exists,
)
from .codegen_shared import CodeGenCpp
from .atoms import CodeGenCpp as CodeGenCppAtomsMon
from hna.hnl.codegen.utils import _split_formula


class CodeGenCpp(CodeGenCpp):
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
        super().__init__(name, args, ctx, fixed_quantifiers, out_dir, namespace)

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

    def _create_instance(self, formula, wr):
        dump_codegen_position(wr)
        args = ",".join(
            chain(
                (str(q.var) for q in formula.quantifier_prefix),
                (f"/* fixed */ {q.var}" for q in self._fixed_quantifiers or ()),
            )
        )

        wr(f"\n  auto *instance = new Instance({args});\n")
        args = ",".join(
            chain(
                (f"{q.var}" for q in self._fixed_quantifiers or ()),
                (str(q.var) for q in formula.quantifier_prefix),
            )
        )
        wr(
            f"    instance->monitor = new sub::HNLMonitor(TS{', ' if args else ''}{args});\n"
        )
        wr(f"    _instances.emplace_back(instance);\n")
        wr("++stats.num_instances;\n\n")
        ns = f"{self._namespace}::" if self._namespace else ""
        wr("#ifdef DEBUG_PRINTS\n")
        print_args = '<< ", " <<'.join(
            (f"{q.var}->id()" for q in formula.quantifier_prefix)
        )
        wr(f'std::cerr << "{ns}::Instance[init, " << {print_args} << "]\\n";')
        wr("#endif /* !DEBUG_PRINTS */\n")

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
        has_submonitors = sub_formula.has_different_quantifiers()
        nested_out_dir = f"{self.out_dir}/submonitor"

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
