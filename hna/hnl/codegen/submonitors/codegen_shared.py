from itertools import chain

from hna.codegen_common.codegen import CodeGen
from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin, basename

from hna.codegen_common.utils import dump_codegen_position
from hna.hnl.formula import ForAllFromFun


class CodeGenCpp(CodeGen):
    """
    Shared methods for CodeGen from atoms.py and submon.py
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
        super().__init__(name, args, ctx, out_dir=out_dir, namespace=namespace)

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_dir, "../templates/")
        self._fixed_quantifiers = fixed_quantifiers

        assert (
            self.args.csv_header
        ), "Give --csv-header, other methods not supported yet"

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

    def _traces_ctors_dtors(self, formula, with_TS=True):
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
            if with_TS:
                wr(
                    f"HNLMonitor::{proto} : TS(TS){', ' if args else ''}{', '.join(args)}"
                )
            else:
                wr(f"HNLMonitor::{proto} : {', '.join(args)}")
            wr("{}\n\n")

        return decls
