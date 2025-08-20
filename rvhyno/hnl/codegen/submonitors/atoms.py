from itertools import chain
from os.path import basename

from pyeda.boolalg.bdd import bddvar

from rvhyno.codegen.utils import dump_codegen_position
from rvhyno.hnl.codegen.bdd import BDDNode, ConstBDDNode
from rvhyno.hnl.formula import Comparison, And, Or, Not, TrivialTrue
from .codegen_shared import CodeGenCpp as CodeGenCppShared


class CodeGenCppAtoms(CodeGenCppShared):
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

        self.BDD = None
        self._bdd_nodes = []
        self._bdd_vars_to_nodes = {}
        self._automata = {}
        self._atoms_files = []

    def copy_files(self):
        # copy files from the CMD line
        for f in self.args.cpp_files:
            self.copy_file(f)

        # copy common templates
        files = [
            "monitor.h",
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
            "atoms_sources": " ".join((basename(f) for f in self._atoms_files)),
            "additional_cflags": " ".join((d for d in self.args.cflags)),
            "CMAKE_BUILD_TYPE": build_type,
            "monitor_name": self.name(),
            "add_submonitors": "\n".join(
                (
                    f"add_subdirectory({submon_dir})"
                    for submon_dir in (d["out_dir"] for d in self._submonitors)
                )
            ),
            "submonitors_libs": " ".join(self._submonitors),
        }
        if overwrite_keys:
            values.update(overwrite_keys)

        if self._embedded:
            cmakelists = "CMakeLists-atoms-embedded.txt.in"
        else:
            cmakelists = "CMakeLists-atoms.txt.in"
        self.gen_file(cmakelists, "CMakeLists.txt", values)

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
            if isinstance(F, Comparison):
                v = bddvar(str(F))
                if isinstance(F, TrivialTrue):
                    # turn the BDD node into TRUE
                    v = v | ~v
                else:
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

        if BDD.is_one() or BDD.is_zero():
            assert not self._bdd_nodes, self._bdd_nodes
            # we have constructed no BDD nodes, because we have only the trivial BDD true/false.
            # But even for true/false, we need to build the atom (a special one).
            # Add this special BDDNode
            self._bdd_nodes.append(ConstBDDNode(formula.formula, BDD))

        self.BDD = BDD

    def _generate_bdd_code(self, formula):

        self.gen_file("formula-state.h.in", "formula-state.h",
                      {'cg': self })

        def bdd_to_action(bdd):
            if bdd.is_one():
                return "RESULT_TRUE"
            elif bdd.is_zero():
                return "RESULT_FALSE"

            nd = self._bdd_vars_to_nodes[bdd.top]
            return f"ATOM_{nd.get_id()}"

        # this is so stupid, but I just cannot get the variable
        # for the node, because PyEDA does not have getters for `_VARS`
        # dictionary. So I'm just generating sub-BDDs from which I
        # can get the root variable.
        with self.new_file("bdd-structure.h") as f:
            dump_codegen_position(f)
            f.write("/* ATOM, ACTION_IF_TRUE, ACTION_IF_FALSE*/\n")
            f.write("constexpr FormulaEvaluationState BDD[][3] = {\n")
            f.write("  {INVALID, INVALID, INVALID},\n")
            rows = {}

            if self.BDD.is_zero() or self.BDD.is_one():
                rows[1] = f"  {{ ATOM_1, RESULT_TRUE, RESULT_FALSE }} ,\n"
            else:
                seen = set()
                wbg = set()
                wbg.add(self.BDD)
                while wbg:
                    bdd = wbg.pop()
                    if bdd in seen:  # or bdd.is_one() or bdd.is_zero():
                        continue
                    seen.add(bdd)

                    hi = bdd.restrict({bdd: 1})
                    lo = bdd.restrict({bdd: 0})
                    wbg.add(hi)
                    wbg.add(lo)

                    if bdd.top:
                        nd = self._bdd_vars_to_nodes[bdd.top]
                        assert nd.get_id() not in rows, rows
                        rows[nd.get_id()] = (
                            f"  {{ {bdd_to_action(bdd)}, {bdd_to_action(hi)}, {bdd_to_action(lo)} }} ,\n"
                        )
                    else:
                        if bdd.is_zero():
                            pass

            idxs = sorted(rows)
            for idx in idxs:
                f.write(rows[idx])

            f.write("};\n\n")

            dump_codegen_position(f)
            # FIXME: TRUE and FALSE BDDs still may break this code,
            # we need to handle them on some higher level (ideally just do not create this instance
            # and immediately solve it)
            BDD = self.BDD
            if BDD.top:
                nd_id = self._bdd_vars_to_nodes[BDD.top].get_id()
            else:
                assert BDD.is_one() or BDD.is_zero(), BDD
                nd_id = 1
            f.write(
                f"static constexpr FormulaEvaluationState INITIAL_ATOM = ATOM_{nd_id};\n"
            )

    def _create_instance(self, formula, wr):
        dump_codegen_position(wr)
        args = ",".join(
            chain(
                (str(q.var) for q in formula.quantifier_prefix),
                (f"/* fixed */ {q.var}" for q in self._fixed_quantifiers or ()),
            )
        )
        print_args = '<< ", " <<'.join(
            (f"{q.var}->id()" for q in formula.quantifier_prefix)
        )
        wr(
            f"""
           auto *instance = new Instance{{{args}, INITIAL_ATOM}};
           ++stats.num_instances;

           instance->monitor = createAtomMonitor(INITIAL_ATOM, *instance);

           #ifdef DEBUG_PRINTS
           std::cerr << "Instance[init, " << {print_args} << "]\\n";
           #endif /* !DEBUG_PRINTS */
        """
        )

    def _generate_hnlinstances(self, formula):

        def trace_variables(nd):
            return [t.name for t in nd.formula.trace_variables()]

        self.gen_file("instance.h.in", "instance.h",
                      {'cg': self, 'formula': formula,
                       'args': [f'Trace *{q.var.name}' for q in
                                chain(formula.quantifier_prefix, self._fixed_quantifiers or ())],
                       'trace_variables': trace_variables
                       })

      # with self.new_file("instance.h") as f:
      #     wr = f.write
      #     wr(
      #         f"""
      #     #ifndef _HNL_INSTANCE_H__{self.name()}
      #     #define _HNL_INSTANCE_H__{self.name()}
      #     """
      #     )
      #     wr("#include <cassert>\n\n")
      #     wr('#include "formula-state.h"\n')
      #     wr('#include "trace.h"\n\n')
      #     wr('#include "atom-identifier.h"\n\n')

      #     f.write(self.namespace_start())
      #     f.write("\n\n")

      #     wr("class AtomMonitor;\n\n")
      #     dump_codegen_position(wr)
      #     wr("struct Instance {\n")
      #     wr("  /* variable traces */\n")
      #     for q in formula.quantifier_prefix:
      #         wr(f"  Trace *{q.var};\n")
      #     wr("  /* fixed traces */\n")
      #     for q in self._fixed_quantifiers or ():
      #         wr(f"  Trace *{q.var};\n")
      #     wr("\n  /* Currently evaluated atom automaton */\n")
      #     wr(f"  FormulaEvaluationState state;\n\n")
      #     wr("  /* The monitor this configuration waits for */\n")
      #     wr("  AtomMonitor *monitor{nullptr};\n\n")
      #     args = (
      #         f"Trace *{q.var}"
      #         for q in chain(formula.quantifier_prefix, self._fixed_quantifiers or ())
      #     )
      #     wr(
      #         f"  Instance({', '.join(args)}, FormulaEvaluationState init_state)\n  : "
      #     )

      #     wr(
      #         ", ".join(
      #             (
      #                 f"{q.var}({q.var})"
      #                 for q in chain(
      #                     formula.quantifier_prefix, self._fixed_quantifiers or ()
      #                 )
      #             )
      #         )
      #     )
      #     wr(", state(init_state) { assert(state != INVALID); }\n\n")

      #     wr("AtomIdentifier createMonitorID(int monitor_type) {")
      #     wr("switch (monitor_type) {")
      #     for nd in self._bdd_nodes:
      #         identifier = f"AtomIdentifier{{ATOM_{nd.get_id()}"
      #         trace_variables = [t.name for t in nd.formula.trace_variables()]
      #         for q in formula.quantifiers():
      #             if q.var.name in trace_variables:
      #                 identifier += f", {q.var.name}->id()"
      #             else:
      #                 identifier += ",0"
      #         identifier += "}"
      #         wr(f"case ATOM_{nd.get_id()}: return {identifier};\n")
      #     wr(f"default: abort();\n")
      #     wr("};\n")
      #     wr("}\n\n")

      #     wr("};\n\n")

      #     f.write(self.namespace_end())
      #     f.write("\n\n")

      #     wr("#endif\n")
