from itertools import chain
from os.path import basename

from rvhyno.codegen.utils import dump_codegen_position
from rvhyno.hnl.codegen.submonitors.atoms_shared import get_atoms_codegen
from rvhyno.hnl.codegen.utils import _split_formula
from rvhyno.hnl.formula import (
    Exists,
)
from rvhyno.utils import msg, log_indent_incr, log_indent_decr
from .codegen_shared import CodeGenCpp


class CodeGenCpp(CodeGenCpp):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.
    """

    def __init__(
        self,
        name,
        args,
        fixed_quantifiers=None,
        out_dir: str = None,
        namespace: str = None,
        embedded: bool = False,
    ):
        super().__init__(name, args, fixed_quantifiers, out_dir, namespace, embedded)

    def generate_cmake(self, overwrite_keys=None):
        """
        `embedded` is True if the HNL monitor is a subdirectory in some other project
        """
        from config import vamos_buffers_DIR

        build_type = self.args.build_type
        if not build_type:
            build_type = '"Debug"' if self.args.debug else "Release"

        values = {
            "vamos-buffers_DIR": vamos_buffers_DIR,
            "additional_sources": " ".join(
                (
                    basename(f)
                    for f in self.args.cpp_files
                    + self.args.add_gen_files
                    + self._add_gen_files
                )
            ),
            "additional_cflags": " ".join((d for d in self.args.cflags)),
            "CMAKE_BUILD_TYPE": build_type,
            "monitor_name": self.name(),
            "add_submonitors": "\n".join(
                (
                    f"add_subdirectory({submon_dir})"
                    for submon_dir in (d["out_dir"] for d in self._submonitors)
                )
            ),
            "submonitors_libs": " ".join((d["name"] for d in self._submonitors)),
        }
        if overwrite_keys:
            values.update(overwrite_keys)

        if self._embedded:
            cmakelists = "sub/CMakeLists-embedded.txt.in"
        else:
            cmakelists = "sub/CMakeLists.txt.in"
        self.gen_file(cmakelists, "CMakeLists.txt", values)

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
            f"    instance->monitor = new sub::FormulaMonitor(TS{', ' if args else ''}{args});\n"
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

    def _generate_instance_h(self, formula):
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
            wr('#include "submonitor/formula-monitor.h"\n\n')

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
            wr("  sub::FormulaMonitor *monitor{nullptr};\n\n")
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
            # wr(", monitor(new sub::FormulaMonitor()")
            wr("{}\n\n")

            wr("};\n\n")

            wr(self.namespace_end())
            wr("\n\n")

            wr("#endif\n")

    def _generate_monitor(self, formula):
        """
        Generate a monitor that actually monitors the body of the formula,
        i.e., it creates and moves with atom monitors.
        """
        self._generate_instance_h(formula)
        self._generate_create_instances(formula)

    def generate(self, formula, gen_tests=True):
        """
        The top-level function to generate code
        """
        top_formula, sub_formula, fixed_quantifiers = _split_formula(formula)
        negate_submonitor_result = isinstance(sub_formula.quantifier_prefix[0], Exists)

        # generate this monitor
        self.generate_monitor(top_formula, negate_submonitor_result)
        # generate the submonitors
        self.generate_submonitors(sub_formula, fixed_quantifiers)

        if not self._embedded:
            self.gen_file(
                "main.cpp.in",
                "main.cpp",
                {
                    "namespace_using": (
                        f"using namespace {self._namespace};" if self._namespace else ""
                    )
                },
            )

        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake()

        self.format_generated_code()

    def generate_submonitors(self, sub_formula, universal_prefix: list):
        has_submonitors = sub_formula.has_different_quantifiers()
        nested_out_dir = f"{self._out_dir}/submonitor"

        msg("dbg", sub_formula, has_submonitors)

        if isinstance(sub_formula.quantifier_prefix[0], Exists):
            sub_formula = sub_formula.negate()

        if has_submonitors:
            nested_cg = CodeGenCpp(
                self.sub_name(),
                self.args,
                fixed_quantifiers=(self._fixed_quantifiers or []) + universal_prefix,
                out_dir=nested_out_dir,
                namespace=self.sub_namespace(),
                embedded=True,
            )
        else:
            nested_cg = get_atoms_codegen(self.args.logic)(
                self.sub_name(),
                self.args,
                fixed_quantifiers=(self._fixed_quantifiers or []) + universal_prefix,
                out_dir=nested_out_dir,
                namespace=self.sub_namespace(),
                embedded=True,
            )
        log_indent_incr()
        nested_cg.generate(sub_formula)
        log_indent_decr()

        self._submonitors = [{"name": self.sub_name(), "out_dir": nested_out_dir}]

    def generate_monitor(self, formula, negate_submonitor_result=False):
        input_traces = self._traces_attribute_str(formula)
        # NOTE: this method generates definitions of ctors and dtors into an .h file,
        # and returns a list of declarations of those ctors and dtors
        ctors_dtors = self._traces_ctors_dtors(formula)
        inputs_finished = self._inputs_finished(formula)

        values = {
            "monitor_name": self.name(),
            "namespace": self.namespace(),
            "sub_namespace": self.sub_namespace(),
            "namespace_start": self.namespace_start(),
            "namespace_end": self.namespace_end(),
            "input_traces": input_traces,
            "inputs_finished": inputs_finished,
            "ctors_dtors": "\n".join(ctors_dtors),
            "process_submonitor_verdict": (
                "verdict = negate_verdict(verdict);" if negate_submonitor_result else ""
            ),
            "info": f"Monitor for '{formula}'",
        }

        self.gen_file("sub/monitor.h.in", "formula-monitor.h", values)
        self.gen_file("sub/monitor.cpp.in", "formula-monitor.cpp", values)

        self._generate_monitor(formula)
