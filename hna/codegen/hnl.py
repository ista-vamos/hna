from itertools import permutations
from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin, basename

from vamos_common.codegen.codegen import CodeGen

from hna.hnl.formula import IsPrefix
from hna.hnl.formula2automata import formula_to_automaton, compose_automata


class CodeGenCpp(CodeGen):
    def __init__(self, args, ctx):
        super().__init__(args, ctx)

        self_path = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_path, "templates/cpp")
        self._formula_to_automaton = {}

    def _copy_common_files(self):
        files = [
            "trace.h",
            "inputs.h",
            "main.cpp"
        ]
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

    def _generate_AnyCfg(self, cfgs):
        """
        This is a union of all configurations. It has smaller overhead than std::variant, so we use this.
        """
        with self.new_file("anycfg.h") as cf:
            wr = cf.write
            wr("#ifndef OD_ANYCFG_H_\n#define OD_ANYCFG_H_\n\n")
            wr('#include "cfgs.h"\n\n')

            wr("struct AnyCfg {\n" f"  unsigned short _idx{{{len(cfgs)}}};\n\n")
            wr("  auto index() const -> auto{ return _idx; }\n\n")

            wr("  union CfgTy {\n")
            wr("    ConfigurationBase none;\n")
            for _, cfg, _ in cfgs:
                wr(f"    {cfg} {cfg.lower()};\n")

            wr("\n    CfgTy() : none() {}\n")
            wr("\n    ~CfgTy() {}\n")
            for _, cfg, _ in cfgs:
                wr(f"    CfgTy({cfg} &&c) : {cfg.lower()}(std::move(c)) {{}}\n")
            wr("  } cfg;\n\n")

            # wr("  template <typename CfgTy> CfgTy &get() { abort(); /*return std::get<CfgTy>(cfg);*/ }\n")
            # for cfg in cfgs:
            #    wr(f"  template <> {cfg} &get() {{ return cfg.{cfg.lower()}; }}\n")

            wr("\n  AnyCfg(){}\n")

            wr("  ~AnyCfg(){\n" "    switch (_idx) {\n")
            for n, cfg, _ in cfgs:
                wr(f"    case {n}: cfg.{cfg.lower()}.~{cfg}(); break;\n")
            wr("    }\n" "   }\n")
            # wr( "  template <typename CfgTy> AnyCfg(CfgTy &&c) : cfg(std::move(c)) { abort(); }\n")
            for n, cfg, _ in cfgs:
                wr(f"  AnyCfg({cfg} &&c) : _idx({n}), cfg(std::move(c)) {{}}\n")

            wr("\n  AnyCfg(AnyCfg &&rhs) : _idx(rhs._idx) {\n" "    switch(_idx) {\n")
            for n, cfg, _ in cfgs:
                wr(
                    f"    case {n}: cfg.{cfg.lower()} = std::move(rhs.cfg.{cfg.lower()}); break;\n"
                )
            wr("    default: break; // do nothing\n" "    }\n  }\n ")

            wr(
                "\n  AnyCfg& operator=(AnyCfg &&rhs) {\n"
                "    _idx = rhs._idx;\n"
                "    switch(_idx) {\n"
            )
            for n, cfg, _ in cfgs:
                wr(
                    f"    case {n}: cfg.{cfg.lower()} = std::move(rhs.cfg.{cfg.lower()}); break;\n"
                )
            wr(
                "    default: break; // do nothing\n"
                "    }\n"
                "    return *this;\n"
                "  }\n "
            )

            wr("};\n\n")
            wr("#endif\n")

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

    def _generate_monitor_core(self, mpt, wr):
        wr("      for (auto &c : C) {\n" "        switch (c.index()) {\n")
        for n, cfg, transition in self.cfgs:
            wr(
                f"        case {n}: /* {cfg} */ {{\n"
                f"          auto &cfg = c.cfg.{cfg.lower()};\n"
                "          if (cfg.failed()) {\n"
                "              continue;\n"
                "          }\n"
                "          non_empty = true;\n"
            )

            if self.args.debug:
                wr(f'          std::cout << "-- " << cfg;\n')
            wr(
                f"          auto move_result = move_cfg<{cfg}, {len(transition.mpe.exprs)}>(new_workbag, cfg);\n"
            )
            if self.args.debug:
                wr(
                    f'          std::cout << "\\n~> " << cfg  << "\\n=> " << actionToStr(move_result) << "\\n";\n'
                )
            wr(
                f"          switch (move_result) {{\n"
                "          case CFGSET_MATCHED:\n"
            )
            out = transition.output
            if out and mpt.has_single_boolean_output():
                assert len(out) == 1, out
                if out[0].value is False:
                    if self.args.debug or self.args.verbose:
                        wr(
                            '            std::cout << "\033[1;31mPROPERTY VIOLATED!\033[0m\\n";\n'
                        )
                    if self.args.exit_on_error:
                        wr("           goto violated;\n")
                elif out[0].value is True:
                    wr("           /* out: true */\n")
                else:
                    raise NotImplementedError(
                        f"Non-boolean output not implemented: {transition.output}"
                    )
            wr("            // fall-through\n")
            wr(
                "          case CFGSET_DONE:\n"
                "            C.setInvalid();\n"
                "            ++wbg_invalid;\n"
                "            goto outer_loop;\n"
                "            break;\n"
                "          case NONE:\n"
                "          case CFG_FAILED: // remove c from C\n"
                "            break;\n"
                "           }\n"
            )
            wr("          break;\n" "          }\n")
        wr(
            "         default:\n"
            '           assert(false && "Unknown configuration"); abort();\n'
            "           }\n"
            "         }\n\n"
            "        if (!non_empty) {\n"
            "           C.setInvalid();\n"
            "        }\n\n"
            "outer_loop:\n"
            "         (void)1;\n\n"
            "  }\n\n"
        )

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
        print(f"sub-formula = {formula}")

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

        self._copy_common_files()
        self._generate_cmake()
        #self._generate_monitor(mpt)


        def gen_automaton(F):
            if not isinstance(F, IsPrefix):
                return
            self.generate_atomic_comparison_automaton(F)

        formula.visit(gen_automaton)

