from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin

from rvhyno.codegen.codegencpp import CodeGenCpp
from rvhyno.codegen.utils import dump_codegen_position
from rvhyno.hnl.formula import ForAllFromFun


class CodeGenCpp(CodeGenCpp):
    """
    Shared methods for CodeGen from atoms/ehl.py, atoms/shl.py and submon.py
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
        super().__init__(
            name=name, args=args, out_dir=out_dir, namespace=namespace, embedded=embedded
        )

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_dir, "../templates/")
        self._fixed_quantifiers = fixed_quantifiers

    def _generate_create_instances(self, formula):
        _, _, q2set = self.input_tracesets(formula)

        with self.new_file("_create-instances.h") as f:
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
                    self._gen_create_instance_reduced(formula, wr)
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
                    wr(f"for (auto &[t{i}_id, t{i}_ptr] : traces) {{\n")
                else:
                    wr(f"for (auto &[t{i}_id, t{i}_ptr] : traces_{ts.c_name()}) {{\n")
                wr(f"  auto *{q.var} = t{i}_ptr;\n")
            if n in new_ns:
                wr(f"if ({q.var} == t_new) {{ continue; }}\n")

        self._create_instance(formula, wr)

        # there is one less } than quantifiers, because we do not generate
        # for loop for the quantifier to which we assign t_new
        for i in range(1, len(formula.quantifier_prefix)):
            wr("}\n")

    def _create_instance(self, formula, wr):
        raise NotImplementedError("Must be overriden")

    def _gen_create_instance_reduced(self, formula, wr):
        raise NotImplementedError("Must be overriden")

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

    def _inputs_finished(self, formula):
        fixed, set2q, q2set = self.input_tracesets(formula)
        # Add attributes for quantifiers fixed by parent monitors
        lines = [
            f"if (!{ts}.finished()) {{ return false; }}"
            for ts in (
                "traces" if traceset is None else f"traces_{traceset.c_name()}"
                for traceset, _ in set2q.items()
            )
        ] + [f"if (!{q}->finished()) {{ return false; }}" for q in (fixed or ())]
        return "\n".join(lines)


    def read_generated_file(self, name):
        """
        Args:
            name: name of the file

        Returns: the contents of the file as string

        Read the contents of a generated file and return it as a string.
        In some cases, it is easier to generate the whole code in Python instead of creating a template for it
        (e.g., for creating the instances of formula). In such cases, we can use this method to feed the
        generated contents into a generated file via a template.
        """
        path = self.get_output_path(name)
        # More efficient would be to return the opened file and then somehow take care of closing it,
        # but for now, this is good enough
        with open(path, 'r') as f:
            return f.readlines()
