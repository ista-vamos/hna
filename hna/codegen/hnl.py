from itertools import permutations
from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin, basename

from vamos_common.codegen.codegen import CodeGen

from hna.hnl.formula import IsPrefix
from hna.hnl.formula2automata import formula_to_automaton, compose_automata


class CodeGenCpp(CodeGen):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.
    """

    def __init__(self, args, ctx):
        super().__init__(args, ctx)

        self_path = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_path, "templates/cpp")
        self._formula_to_automaton = {}

    def _copy_common_files(self):
        files = ["trace.h", "main.cpp"]
        for f in files:
            if f not in self.args.overwrite_default:
                self.copy_file(f)

        for f in self.args.cpp_files:
            self.copy_file(f)

    def _generate_cmake(self):
        from config import vamos_buffers_DIR

        build_type = self.args.build_type
        if not build_type:
            build_type = '"Debug"' if self.args.debug else ""

        self.gen_config(
            "CMakeLists.txt.in",
            "CMakeLists.txt",
            {
                "@vamos-buffers_DIR@": vamos_buffers_DIR,
                "@additional_sources@": " ".join(
                    (basename(f) for f in self.args.cpp_files + self.args.add_gen_files)
                ),
                "@additional_cmake_definitions@": " ".join(
                    (d for d in self.args.cmake_defs)
                ),
                "@CMAKE_BUILD_TYPE@": build_type,
            },
        )

    def _generate_add_cfgs(self, mpt, wr):
        wr("template <typename TracesT>\n")
        wr(
            "static void add_new_cfgs(WorkbagTy &workbag, const TracesT &traces, Trace<TraceEvent> *trace) {\n"
        )
        wr(f"  ConfigurationsSetTy S;\n")
        N = len(mpt.traces_in) - 1
        assert N < mpt.get_max_outdegree(), mpt

        for i in range(0, N):
            wr(f"  for (auto &t{i} : traces) {{\n")

        if "reflexivity" in self.args.reduction:
            cond = " && ".join((f"trace == t{i}.get()" for i in range(0, N)))
            wr(f"    if ({cond}) // reduction: reflexivity\n" "      continue;\n\n")
        wr("    S.clear();\n")

        assert self.cfgs

        if "symmetry" in self.args.reduction:
            traces = ", ".join(
                f"t{i}.get()" if i != N else "trace" for i in range(0, N + 1)
            )
            for n, cfg, transition in self.cfgs:
                if not mpt.is_init_transition(transition):
                    continue
                wr(f"    S.add({cfg}({{{traces}}}));\n")
            wr("    workbag.push(std::move(S));\n")
        else:
            for idx, P in enumerate(permutations(range(0, N + 1))):
                if idx > 0:
                    wr("\n    S.clear();\n")
                traces = ", ".join(f"t{i}.get()" if i != N else "trace" for i in P)
                for n, cfg, transition in self.cfgs:
                    if not mpt.is_init_transition(transition):
                        continue
                    wr(f"    S.add({cfg}({{{traces}}}));\n")
                wr("    workbag.push(std::move(S));\n")

        for i in range(0, N):
            wr("  }\n")

        wr("}\n\n")

    def _generate_cfg(self, mpt, transition, cf, cfcpp, mfwr):
        mpe_name = self._generate_mpe(transition, mfwr)
        cfg_name = f"Cfg_{transition.start.name}_{transition.end.name}"
        cfwr = cf.write
        K = len(transition.mpe.exprs)
        cfwr(
            f"class {cfg_name} : public Configuration <Trace<TraceEvent>, {K}> {{\n\n"
            f"  {mpe_name} mPE;\n\n"
            "public:\n"
            f"  {cfg_name}(const std::array<Trace<TraceEvent> *, {K}> &tr) : Configuration(tr) {{}}\n"
            f"  {cfg_name}(const std::array<Trace<TraceEvent> *, {K}> &tr, size_t pos[{K}]) : Configuration(tr, pos) {{}}\n\n"
            f"  static constexpr size_t TRACES_NUM = {len(transition.mpe.exprs)};\n\n"
            f"  void queueNextConfigurations(WorkbagBase& workbag);\n\n"
        )

        self.input_file(cf, "partials/cfg_methods.h")

        cfwr("};\n\n")
        cfwr(f"std::ostream &operator<<(std::ostream &s, const {cfg_name}& c);\n\n")

        wr = cfcpp.write
        wr(f"void {cfg_name}::queueNextConfigurations(WorkbagBase& workbag) {{\n")
        cond = ", ".join(f"trace({i})" for i in range(0, K))
        wr(f"  assert (mPE.accepted() && mPE.cond({cond}));\n\n")
        S = mpt.successors(transition)
        if S:
            wr(f"  ConfigurationsSet<{mpt.get_max_outdegree()}> S;\n\n")
            for succ in S:
                succ_cfg_name = f"Cfg_{succ.start.name}_{succ.end.name}"
                wr(f"  S.add({succ_cfg_name}(traces, positions));\n")
            wr(
                f"  static_cast<Workbag<ConfigurationsSet<{mpt.get_max_outdegree()}>>&>(workbag).push(std::move(S));\n"
            )
        wr("}\n\n")

        if self.args.debug:
            wr(
                f"std::ostream &operator<<(std::ostream & s, const {cfg_name}& c) {{\n"
                f'  s << "{cfg_name} {{fail: " << c.failed() << ", pos=[" '
            )
            for i in range(0, K):
                if i > 0:
                    wr('<< ", " ')
                wr(f"<< c.pos({i})")

            wr('  << "], next: [";\n')
            for i in range(0, K):
                if i > 0:
                    wr('s << ", ";\n')
                wr(
                    f"if (c.next_event({i})) {{\n"
                    f"  s <<  *static_cast<const TraceEvent*>(c.next_event({i})); }}\n"
                    ' else { s << "nil"; }\n'
                )

            wr('  s << "]}";\n')
            wr(f"  return s;\n" "}\n\n")

        return cfg_name

    def _generate_cfgs(self, mpt):
        mf = self.new_file("mpes.h")
        cf = self.new_file("cfgs.h")
        cfcpp = self.new_file("cfgs.cpp")
        self.input_file(cfcpp, "partials/cfgs.cpp")

        mfwr = mf.write
        mfwr("#ifndef OD_MPES_H_\n#define OD_MPES_H_\n\n")
        mfwr('#include "trace.h"\n\n')
        mfwr('#include "prefixexpr.h"\n\n')
        mfwr('#include "subword-compare.h"\n\n')

        cfwr = cf.write
        cfwr("#ifndef OD_CFGS_H_\n#define OD_CFGS_H_\n\n")
        cfwr('#include "mpes.h"\n')
        cfwr('#include "cfg.h"\n\n')
        cfwr("class WorkbagBase;\n\n")
        if self.args.debug:
            cfwr("#include <iostream>\n\n")

        cfgs = []
        for n, transition in enumerate(mpt.transitions):
            cfg_name = self._generate_cfg(mpt, transition, cf, cfcpp, mfwr)
            cfgs.append((n, cfg_name, transition))

        self._generate_AnyCfg(cfgs)
        self.cfgs = cfgs

        mfwr("#endif")
        cfwr("#endif")
        mf.close()
        cf.close()
        cfcpp.close()

    def _generate_events(self, formula):
        with self.new_file("events.h") as f:
            wr = f.write
            wr("#ifndef EVENTS_H_\n#define EVENTS_H_\n\n")
            # wr("#include <cassert>\n\n")

            wr("struct Event {\n")
            for letter in formula.constants():
                wr(f"  /* FIELD {letter} */\n")
            wr("};\n\n")

            wr("#endif\n")

        with self.new_file("events.cpp") as f:
            wr = f.write

    def _generate_csv_reader(self):
        with self.new_file("inputs.h") as f:
            wr = f.write
            wr("#ifndef INPUTS_H_\n#define INPUTS_H_\n\n")
            # wr("#include <cassert>\n\n")

            wr("class Inputs {\n")
            for letter in formula.constants():
                wr(f"  /* FIELD {letter} */\n")
            wr("};\n\n")

            wr("#endif\n")

    def _generate_monitor_core(self, mpt, wr):
        wr("/* MONITOR CORE *?\n")

    def _generate_monitor(self, mpt):
        with self.new_file("monitor.cpp") as f:
            wr = f.write
            wr("#include <iostream>\n")
            wr("#include <cassert>\n\n")

            wr('#include "events.h"\n')
            wr('#include "monitor.h"\n')
            wr('#include "trace.h"\n')
            wr('#include "cfgset.h"\n')
            wr('#include "workbag.h"\n')
            wr('#include "inputs.h"\n\n')

            wr('#include "cfgs.h"\n\n')

            wr(
                f"using ConfigurationsSetTy = ConfigurationsSet<{mpt.get_max_outdegree()}>;\n"
            )
            wr(f"using WorkbagTy = Workbag<ConfigurationsSetTy>;\n\n")

            self._generate_add_cfgs(mpt, wr)

            self.input_file(f, "partials/update_traces.h")
            self.input_file(f, "partials/move_cfg.h")

            self.input_file(f, "partials/monitor_begin.h")
            self._generate_monitor_core(mpt, wr)
            self.input_file(f, "partials/monitor_end.h")

    def generate_atomic_comparison_automaton(self, formula):
        num = len(self._formula_to_automaton) + 1

        alphabet = formula.constants()
        A1 = formula_to_automaton(formula.children[0], alphabet)
        A2 = formula_to_automaton(formula.children[1], alphabet)
        A = compose_automata(A1, A2)

        if self.args.debug:
            with self.new_dbg_file(f"aut-{num}-lhs.dot") as f:
                A1.to_dot(f)
            with self.new_dbg_file(f"aut-{num}-rhs.dot") as f:
                A2.to_dot(f)
            with self.new_dbg_file(f"aut-{num}.dot") as f:
                A.to_dot(f)

    def generate(self, formula):
        """
        The top-level function to generate code
        """

        self._copy_common_files()
        self._generate_cmake()
        self._generate_events(formula)
        # self._generate_monitor(mpt)

        def gen_automaton(F):
            if not isinstance(F, IsPrefix):
                return
            self.generate_atomic_comparison_automaton(F)

        formula.visit(gen_automaton)
