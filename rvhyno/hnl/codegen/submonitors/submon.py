from itertools import chain
from os.path import basename

from rvhyno.codegen.utils import dump_codegen_position
from rvhyno.hnl.formula import (
    Exists,
)
from .codegen_shared import CodeGenCpp
from rvhyno.hnl.codegen.submonitors.atoms_shared import get_atoms_codegen
from rvhyno.hnl.codegen.utils import _split_formula


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
            cmakelists = "CMakeLists-sub-embedded.txt.in"
        else:
            cmakelists = "CMakeLists-sub.txt.in"
        self.gen_file(cmakelists, "CMakeLists.txt", values)

  # def _generate_monitor(self, formula):
  #     """
  #     Generate a monitor that actually monitors the body of the formula,
  #     i.e., it creates and moves with atom monitors.
  #     """
  #     self._generate_hnlinstances(formula)
  #     self._generate_create_instances(formula)

    def generate(self, formula, gen_tests=True):
        """
        The top-level function to generate code
        """
        top_formula, sub_formula, fixed_quantifiers = _split_formula(formula)
        negate_submonitor_result = isinstance(sub_formula.quantifier_prefix[0], Exists)

        # generate this monitor
        self.generate_monitor(top_formula, negate_submonitor_result)
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
        nested_out_dir = f"{self.out_dir}/submonitor"

        print("XXX", sub_formula, has_submonitors)

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
                embedded=True,
            )
        else:
            nested_cg = get_atoms_codegen(self.args.logic)(
                self.sub_name(),
                self.args,
                self.ctx,
                fixed_quantifiers=(self._fixed_quantifiers or []) + universal_prefix,
                out_dir=nested_out_dir,
                namespace=self.sub_namespace(),
                embedded=True,
            )
        nested_cg.generate(sub_formula)
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
            "sub-namespace": self.sub_namespace(),
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

        self.gen_file("hnl-sub-monitor.h.in", "hnl-monitor.h", values)
        self.gen_file("hnl-sub-monitor.cpp.in", "hnl-monitor.cpp", values)

        self._generate_monitor(formula)
