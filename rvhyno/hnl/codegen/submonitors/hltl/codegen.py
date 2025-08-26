from itertools import chain
from os.path import basename

from rvhyno.codegen.utils import dump_codegen_position
from rvhyno.hnl.formula import PrenexFormula
from ..shared import CodeGenCpp
from rvhyno.utils import msg

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


    def generate(self, formula, gen_tests=True):
        """
        The top-level method to generate code
        """

        self.generate_monitor(formula)

        if gen_tests:
            msg('warn', "Cannot generate tests for HLTL monitors")

        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake()

        self.format_generated_code()

    # def _generate_trivial_atom(self, nd):
    #     num, F = nd.get_id(), nd.formula
    #
    #     if nd.bddvar.is_one():
    #         result = "Verdict::TRUE"
    #     elif nd.bddvar.is_zero():
    #         result = "Verdict::FALSE"
    #     else:
    #         raise NotImplementedError("Unknown BDD node")
    #
    #     values = {
    #         "monitor_name": self.name(),
    #         "namespace": self.namespace(),
    #         "namespace_start": self.namespace_start(),
    #         "namespace_end": self.namespace_end(),
    #         # "info": f"Monitor for '{nd.formula}'",
    #         "formula": str(nd.formula),
    #         "verdict": result,
    #         "atom_num": str(num),
    #     }
    #
    #     self.gen_file("atoms/trivial-atom-monitor.h.in", f"atom-{num}.h", values)


    def generate_monitor(self, formula: PrenexFormula):

        msg('info', "Generating monitor code", section=3)
        # NOTE: this code must come after _gen_bdd_from_formula as it uses the nodes
        assert not formula.has_quantifier_alternation(), formula
        inputs_finished = self._inputs_finished(formula)

        values = {
            "cg": self,
            "monitor_name": self.name(),
            "namespace": self.namespace(),
            "namespace_start": self.namespace_start(),
            "namespace_end": self.namespace_end(),
            "inputs_finished": inputs_finished,
            "formula": formula,
        }

        self.gen_file("hltl/formula-monitor.h.in", "formula-monitor.h", values)
        self.gen_file("hltl/formula-monitor.cpp.in", "formula-monitor.cpp", values)


    def generate_cmake(self, overwrite_keys=None):
        """
        `embedded` is True if the HNL monitor is a subdirectory in some other project
        """
        from config import vamos_buffers_DIR

        build_type = self.args.build_type
        if not build_type:
            build_type = '"Debug"' if self.args.debug else "Release"

        values = {
            # "vamos-buffers_DIR": vamos_buffers_DIR,
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
            "monitor_name": self.name()
        }
        if overwrite_keys:
            values.update(overwrite_keys)

        if self._embedded:
            cmakelists = "hltl/CMakeLists-embedded.txt.in"
        else:
            raise NotImplementedError("This monitor should be always embedded")
            #cmakelists = "hltl/CMakeLists.txt.in"
        self.gen_file(cmakelists, "CMakeLists.txt", values)

