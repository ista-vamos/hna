import random
from os import makedirs

from hna.automata.automaton import Automaton
from hna.automata.transducers import Var, Reg
from hna.codegen_common.utils import dump_codegen_position
from hna.hnl.codegen.bdd import BDDNode
from hna.hnl.formula import (
    IsPrefix,
    PrenexFormula,
)
from hna.hnl.formula2automata import (
    formula_to_automaton,
    compose_automata,
    to_priority_automaton,
)
from .atoms import CodeGenCppAtoms
from ...formula2transducers import formula_to_transducer, automaton_for_prefixing


def subst_lst(c, lst):
    for s in lst:
        c = c.subst(s)
    return c


def condition_code(t, subst=None):
    cond = t.label.condition
    if subst:
        c_cond = "&&".join(subst_lst(c, subst or []).c_code() for c in cond)
    else:
        c_cond = "&&".join(c.c_code() for c in cond)

    if c_cond == "":
        return "true"
    return c_cond


class CodeGenCpp(CodeGenCppAtoms):
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
        embedded: bool = False,
    ):
        super().__init__(
            name, args, ctx, fixed_quantifiers, out_dir, namespace, embedded
        )

    def _generate_atom_monitor(self):
        with self.new_file("create-atom-monitor.h") as f:
            dump_codegen_position(f)
            f.write("switch(monitor_type) {\n")
            for nd in self._bdd_nodes:
                num = nd.get_id()
                f.write(
                    f"case ATOM_{num}: monitor = new AtomMonitor{num}(instance); break;\n"
                )
            f.write("default: abort();\n")
            f.write("}\n\n")

    def _generate_monitor(self, formula):
        """
        Generate a monitor that actually monitors the body of the formula,
        i.e., it creates and moves with atom monitors.
        """
        self._generate_bdd_code(formula)
        self._generate_hnlinstances(formula)
        self._generate_create_instances(formula)
        self._generate_automata_code(formula)
        self._generate_atom_monitor()

    def _generate_automata_code(self, formula):
        generated_automata = {}
        for nd in self._bdd_nodes:
            print("Generating code for", nd.get_id(), ":", nd.formula)
            assert nd.automaton

            num, F = nd.get_id(), nd.formula
            # duplicate_num = generated_automata.get(
            #    (nd.lvar, nd.rvar, nd.automaton.get_id())
            # )
            # if duplicate_num is not None:
            #    with self.new_file(f"atom-{num}.h") as fh, self.new_file(
            #        f"atom-{num}.cpp"
            #    ) as fcpp:
            #        self._generate_duplicate_atom(
            #            nd, duplicate_num, fh.write, fcpp.write
            #        )
            #        self._atoms_files.append(f"atom-{num}.cpp")
            #    continue

            with self.new_file(f"atom-{num}.h") as fh:
                self._generate_atom_header(F, nd.automaton, num, fh.write)

            with self.new_file(f"atom-{num}.cpp") as fcpp:
                self._generate_atom(fcpp.write, formula, nd)
            self._atoms_files.append(f"atom-{num}.cpp")
            generated_automata[(nd.lvar, nd.rvar, nd.automaton.get_id())] = num

        with self.new_file("atom-identifier.h") as f:
            ns = self.namespace()
            f.write(
                f"""
            #ifndef _ATOM_IDENTIFIER_H__{self.name()}
            #define _ATOM_IDENTIFIER_H__{self.name()}

            #include <tuple>
            """
            )
            dump_codegen_position(f)
            if ns:
                f.write(f"namespace {ns} {{\n\n")
            f.write(
                "\n"
                "// An object that can uniquely identify an atom monitor\n"
                "// by its type and ids of the instantiated traces (or 0 if the trace variable"
                "// is not used by the atom).\n"
            )
            f.write("using AtomIdentifier = std::tuple<unsigned")
            f.write(", unsigned" * len(formula.quantifiers()))
            f.write("> ;\n")
            if ns:
                f.write(f"}} // namespace {self.name()}\n\n")
            f.write("#endif\n")

        with self.new_file("atoms.h") as f:
            f.write(
                f"""
            #ifndef _ATOMS_H__{self.name()}
            #define _ATOMS_H__{self.name()}
            """
            )
            dump_codegen_position(f)
            for nd in self._bdd_nodes:
                f.write(f'#include "atom-{nd.get_id()}.h"\n')
            f.write("#endif\n")

        with self.new_file("do_step.h") as f:
            dump_codegen_position(f)
            f.write("switch (M->type()) {")
            for nd in self._bdd_nodes:
                num = nd.get_id()
                f.write(
                    f"  case {num}: return static_cast<AtomMonitor{num}*>(M)->step();\n"
                )
            f.write(
                f"  case FINISHED: return static_cast<FinishedAtomMonitor*>(M)->step();\n"
            )
            f.write("  default: abort();\n")
            f.write("}")

    def _generate_atom(self, wrcpp, formula, nd):
        atom_formula, num, automaton = nd.formula, nd.get_id(), nd.automaton

        t1 = nd.ltrace.name if nd.ltrace else None
        t2 = nd.rtrace.name if nd.rtrace else None
        if not (t1 or t2):
            raise NotImplementedError("This case is unsupported yet")
        if not t1:
            raise NotImplementedError("This case is unsupported yet")

        wrcpp(f'#include "atom-{num}.h"\n\n')
        if self._namespace:
            wrcpp(f"using namespace {self._namespace};\n\n")
        dump_codegen_position(wrcpp)

        identifier = "AtomIdentifier{st"
        for q in formula.quantifiers():
            if q.var.name in (t1, t2):
                identifier += f",instance.{q.var.name}->id()"
            else:
                identifier += ",0"
        identifier += "}"
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const Instance& instance, FormulaEvaluationState st, Trace *lt, Trace *rt) \n  :"
            f" RegularAtomMonitor({identifier}, lt, rt) {{\n\n"
        )
        assert (
            len(automaton.initial_states()) == 1
        ), f"Automaton {num} has multiple initial states"
        wrcpp(
            f"_cfgs.emplace_back({automaton.get_state_id(automaton.initial_states()[0])}, 0, 0);\n"
        )
        wrcpp("}\n\n")

        t1_instance = f"instance.{t1}" if t1 else "nullptr"
        t2_instance = f"instance.{t2}" if t2 else "nullptr"
        identifier = f"AtomIdentifier{{ATOM_{num}"
        for q in formula.quantifiers():
            if q.var.name in (t1, t2):
                identifier += f",instance.{q.var.name}->id()"
            else:
                identifier += ",0"
        identifier += "}"
        dump_codegen_position(wrcpp)
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const Instance& instance) \n  : AtomMonitor{num}(instance, ATOM_{num}, {t1_instance}, {t2_instance}) {{\n\n"
        )
        assert (
            len(automaton.initial_states()) == 1
        ), f"Automaton {num} has multiple initial states"
        wrcpp("}\n\n")

        wrcpp(f"/* THE AUTOMATON FOR THE ATOM */\n")
        for state in automaton.states():
            wrcpp(f"/* {state} */\n")
        wrcpp("/* --- */\n")
        for t in automaton.transitions():
            wrcpp(f"/* {t} */\n")
        wrcpp("/* --- */\n\n")

        dump_codegen_position(wrcpp)
        assert (
            len(automaton.accepting_states()) > 0
        ), f"Automaton {num} has no accepting states"
        wrcpp("static inline bool state_is_accepting(State s) {")
        wrcpp(" switch (s) {")
        for i in (automaton.get_state_id(s) for s in automaton.accepting_states()):
            wrcpp(f" case {i}: return true;")
        wrcpp(" default: return false;")
        wrcpp(" };")
        wrcpp("}\n\n")

        self.gen_handle_state(num, atom_formula, automaton, wrcpp)

        dump_codegen_position(wrcpp)
        wrcpp(
            "// FIXME: only modify configuration if it has a single possible successor\n"
        )

        wrcpp(
            f"void AtomMonitor{num}::_step(Atom{num}EvaluationState &cfg, const Event *ev1, const Event *ev2) {{\n"
        )

        dump_codegen_position(wrcpp)
        if len(automaton.states()) == 1:
            wrcpp("/* FIXME: do not generate the switch for a single state */\n")
        wrcpp(f"  switch (cfg.state) {{\n")
        for state in automaton.states():
            transitions = automaton.transitions(state)
            transitions = list(transitions.values()) if transitions else []
            # assert transitions == [t for t in automaton.transitions() if t.source == state]
            wrcpp(f" /* {state} */\n ")
            wrcpp(f" case {automaton.get_state_id(state)}:\n ")
            if not transitions:
                wrcpp("/* DROP CFG */\n\n")
                continue
            else:
                wrcpp(f"stepState_{automaton.get_state_id(state)}(cfg, ev1, ev2);\n")
                wrcpp(f"break;\n")

        wrcpp(f" default : abort();\n ")
        wrcpp("  };\n")
        wrcpp("}\n\n")

        ns = f"{self._namespace}::" if self._namespace else ""

        wrcpp(f"Verdict AtomMonitor{num}::step(unsigned /* num_steps */) {{\n")
        wrcpp(
            f"""
            // No more configurations and we have not accepted.
            // That means we reject.
            if (_cfgs.empty()) {{
              return Verdict::FALSE;
            }}
            
            for (auto& cfg : _cfgs) {{
                // XXX: because we already copy the event (instead of using a pointer
                // -- which we cannot use because of the concurrency), we can store the
                // known event in the configuration and always wait only for the unknown one.
                // Would that be more efficient? (It also means bigger configurations...)
            """
        )
        if t1:
            wrcpp(
                f"""
                    Event ev1;
                    auto ev1ty = t1->get(cfg.p1, ev1);
                    if (ev1ty == TraceQuery::WAITING) {{
                        _cfgs.push_new(cfg);
                        continue;
                    }}
                """
            )
        else:
            wrcpp("constexpr auto ev1ty = TraceQuery::END;")
        if t2:
            wrcpp(
                f"""
                    Event ev2;
                    auto ev2ty = t2->get(cfg.p2, ev2);
                    if (ev2ty == TraceQuery::WAITING) {{
                        _cfgs.push_new(cfg);
                        continue;
                    }}
                """
            )
        else:
            wrcpp("constexpr auto ev2ty = TraceQuery::END;")
        t1id = "t1->id()" if t1 else '"-"'
        t2id = "t2->id()" if t2 else '"-"'
        wrcpp(
            f"""
                #ifdef DEBUG_PRINTS
                std::cerr << "{ns}Atom " << type() << " [" << {t1id} << ", " << {t2id} << "] @ (" << cfg.state  << ", " << cfg.p1 << ", " << cfg.p2 << "): ";
            """
        )
        if t1:
            wrcpp(
                f"""
                    if (ev1ty == TraceQuery::END) {{
                        std::cerr << "END";
                    }} else {{
                        std::cerr << ev1;
                    }}
                """
            )
        else:
            wrcpp('std::cerr << "-";')
        wrcpp('std::cerr << ", ";\n')
        if t2:
            wrcpp(
                f"""
                    if (ev2ty == TraceQuery::END) {{
                        std::cerr << "END";
                    }} else {{
                        std::cerr << ev2;
                    }}
                """
            )
        else:
            wrcpp('std::cerr << "-";')
        wrcpp(
            f"""
                std::cerr << "\\n";
                #endif /* !DEBUG_PRINTS */
            """
        )
        if t1:
            wrcpp(
                f"""
                    if (ev1ty == TraceQuery::END) {{
                        if (state_is_accepting(cfg.state)) {{
                            return Verdict::TRUE;
                        }}
                    }}
            """
            )
        else:
            assert t2
            wrcpp(
                f"""
                    if (ev2ty == TraceQuery::END) {{
                        if (state_is_accepting(cfg.state)) {{
                            return Verdict::TRUE;
                        }}
                    }}
            """
            )
        ev1 = "ev1ty == TraceQuery::END ? nullptr : &ev1" if t1 else "nullptr"
        ev2 = "ev2ty == TraceQuery::END ? nullptr : &ev2" if t2 else "nullptr"
        wrcpp(f"_step(cfg, {ev1}, {ev2});")
        wrcpp("}\n")

        wrcpp(f"_cfgs.rotate();")
        wrcpp(" return Verdict::UNKNOWN;\n")
        wrcpp("}\n\n")

    def _generate_atom_header(self, atom_formula, automaton, num, wrh):
        wrh(
            f"""
        #ifndef _ATOM_{num}_H__{self.name()}
        #define _ATOM_{num}_H__{self.name()}
        """
        )
        dump_codegen_position(wrh)
        wrh('#include "regular-atom-monitor.h"\n\n')
        wrh('#include "atom-identifier.h"\n\n')
        wrh('#include "atom-evaluation-state.h"\n\n')

        wrh(self.namespace_start())
        wrh("\n\n")

        dump_codegen_position(wrh)
        wrh(f"struct Atom{num}EvaluationState : public EvaluationState {{\n\n")
        wrh("  /* registers */\n ")
        for r in automaton.registers():
            wrh(f"  Event {r.c_name()};\n")
        wrh("};\n\n")

        dump_codegen_position(wrh)
        wrh(f"/* {atom_formula}*/\n")
        wrh(f"class AtomMonitor{num} : public RegularAtomMonitor {{\n\n")
        for state in automaton.states():
            dump_codegen_position(wrh)
            wrh(
                f"void stepState_{automaton.get_state_id(state)}(Atom{num}EvaluationState& cfg, const Event *ev1, const Event *ev2);\n"
            )
        wrh(
            f"void _step(Atom{num}EvaluationState &cfg, const Event *ev1, const Event *ev2);\n"
        )
        wrh("public:\n")
        wrh(f"AtomMonitor{num}(const Instance& instance);\n\n")
        wrh(
            f"AtomMonitor{num}(const Instance& instance, FormulaEvaluationState st, Trace *lt, Trace *rt);\n\n"
        )
        wrh(f"Verdict step(unsigned num = 0);\n\n")
        wrh("};\n\n")
        wrh(self.namespace_end())
        wrh("\n\n")
        wrh("#endif\n")

    def _generate_duplicate_atom(self, nd, duplicate_of, wrh, wrcpp):
        num, atom_formula = nd.get_id(), nd.formula

        wrh(
            f"""
        #ifndef _ATOM_{num}_H__{self.name()}
        #define _ATOM_{num}_H__{self.name()}
        """
        )
        dump_codegen_position(wrh)
        wrh(f'#include "atom-{duplicate_of}.h"\n\n')

        wrh(self.namespace_start())
        wrh("\n\n")

        dump_codegen_position(wrh)
        wrh(f"/* {atom_formula} */\n\n")
        wrh(
            f"/* This atom is a duplicate of AtomMonitor{duplicate_of} (but possibly trace inputs) */\n"
        )
        wrh(
            f"class AtomMonitor{num} : public AtomMonitor{duplicate_of} {{\n"
            "public:\n"
            f"  AtomMonitor{num}(const Instance&);\n"
            f"}};\n"
        )

        wrh(self.namespace_end())
        wrh("\n\n")
        wrh("#endif\n")

        wrcpp(f'#include "atom-{num}.h"\n\n')
        if self._namespace:
            wrcpp(f"using namespace {self._namespace};\n\n")

        dump_codegen_position(wrcpp)
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const Instance& instance) \n  : AtomMonitor{duplicate_of}(instance, ATOM_{num}, instance.{nd.ltrace}, instance.{nd.rtrace}) {{}}\n\n"
        )

    def gen_handle_state(self, aut_num, atom_formula, automaton, wrcpp):

        lvar = atom_formula.children[0].program_variables()
        rvar = atom_formula.children[1].program_variables()
        assert len(lvar) <= 1, lvar
        assert len(rvar) <= 1, rvar
        lvar = lvar[0].name if lvar else None
        rvar = rvar[0].name if rvar else None
        if not (lvar or rvar):
            raise NotImplementedError("This case is unsupported yet")
        if not lvar:
            raise NotImplementedError("This case is unsupported yet")

        for state in automaton.states():
            dump_codegen_position(wrcpp)
            wrcpp(
                f"void AtomMonitor{aut_num}::stepState_{automaton.get_state_id(state)}(Atom{aut_num}EvaluationState& cfg, const Event *ev1, const Event *ev2) {{\n"
            )

            wrcpp(" bool matched = false;\n")

            self.gen_transitions_code(automaton, state, lvar, rvar, wrcpp)

            wrcpp("}\n\n ")

    def gen_transitions_code(self, automaton, state, lvar, rvar, wrcpp):
        transitions = automaton.transitions_from(state)

        for t in transitions:
            symbol = t.label.symbol
            ### Handle epsilon steps
            if symbol[0].is_eps():
                if symbol[1].is_eps():
                    self.handle_epsilon_step(automaton, t, lvar, rvar, wrcpp)
                else:
                    ### Handle left-epsilon steps
                    self.handle_left_epsilon_step(automaton, t, lvar, rvar, wrcpp)
            elif symbol[1].is_eps():
                ### Handle right-epsilon steps
                self.handle_right_epsilon_step(automaton, t, lvar, rvar, wrcpp)
            else:
                ### Handle letters
                self.handle_symbols(automaton, t, lvar, rvar, wrcpp)
        dump_codegen_position(wrcpp)
        wrcpp("if (matched) { return; }")
        # otherwise the matching failed
        wrcpp(
            "else {  \n"
            "     #ifdef DEBUG_PRINTS\n"
            f'    std::cerr << "    => no transition matched\\n";\n'
            "     #endif /* !DEBUG_PRINTS */\n"
            "     /* this was the least priority, drop the cfg */\n"
            "     return;"
            "}\n\n"
        )

    def handle_symbols(self, automaton, t, lvar, rvar, wrcpp):
        dump_codegen_position(wrcpp)
        symbol = t.label.symbol
        l_automaton_registers = automaton.origin()[0].registers() or ()
        reg_substitution = [
            (r, Reg(f"cfg.{r.c_name()}.{lvar if r in l_automaton_registers else rvar}"))
            for r in automaton.registers()
        ]
        cond = condition_code(
            t,
            [(symbol[0], Var(f"ev1->{lvar}")), (symbol[1], Var(f"ev2->{rvar}"))]
            + reg_substitution,
        )
        wrcpp(f" if (ev1 && ev2 && {cond}) {{\n ")
        wrcpp(
            f" /* {t} */\n "
            "#ifdef DEBUG_PRINTS\n"
            f' std::cerr << "  -- {lvar} = {symbol[0]}; {rvar} = {symbol[1]} -->\\n";\n'
            "#endif /* !DEBUG_PRINTS */\n"
        )
        # wrcpp(f" if (ev1->{lvar} == {symbol[0]} && ev2->{rvar} == {symbol[1]}) {{\n")
        wrcpp(
            f"   matched = true;\n "
            f"  _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1 + 1, cfg.p2 + 1);\n "
        )
        wrcpp(
            "#ifdef DEBUG_PRINTS\n"
            f'   std::cerr << "    => new (" <<_cfgs.back_new().state  << ", " << _cfgs.back_new().p1 << ", " << _cfgs.back_new().p2 << ")\\n";\n'
            "#endif /* !DEBUG_PRINTS */\n"
        )
        # wrcpp("}\n")
        wrcpp("}\n")

    def handle_right_epsilon_step(self, automaton, t, lvar, rvar, wrcpp):
        dump_codegen_position(wrcpp)
        symbol = t.label.symbol
        cond = condition_code(
            t,
            [(symbol[0], Var(f"ev1->{lvar}"))]
            + [(r, Reg(f"cfg.{r.c_name()}.{lvar}")) for r in automaton.registers()],
        )
        wrcpp(f" if (ev1 != nullptr && {cond}) {{\n")
        wrcpp(
            f" /* {t} */\n "
            "#ifdef DEBUG_PRINTS\n"
            f' std::cerr << "  -- {lvar} = {symbol[0]}; {rvar} = {symbol[1]} -->\\n";\n'
            "#endif /* !DEBUG_PRINTS */\n"
        )
        # wrcpp(f" if (ev1->{lvar} == {symbol[0]}) {{\n")
        wrcpp(
            f"   matched = true;\n "
            f"  _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1 + 1, cfg.p2);\n "
        )
        wrcpp(
            "#ifdef DEBUG_PRINTS\n"
            f'   std::cerr << "    => new (" <<_cfgs.back_new().state  << ", " << _cfgs.back_new().p1 << ", " << _cfgs.back_new().p2 << ")\\n";\n'
            "#endif /* !DEBUG_PRINTS */\n"
        )
        # wrcpp("}\n")
        wrcpp("}\n")

    def handle_left_epsilon_step(self, automaton, t, lvar, rvar, wrcpp):

        dump_codegen_position(wrcpp)
        symbol = t.label.symbol
        l_automaton_registers = automaton.origin()[0].registers() or ()
        reg_substitution = [
            (r, Reg(f"cfg.{r.c_name()}.{lvar if r in l_automaton_registers else rvar}"))
            for r in automaton.registers()
        ]
        cond = condition_code(t, [(symbol[1], Var(f"ev2->{rvar}"))] + reg_substitution)
        wrcpp(f" if (ev2 != nullptr && {cond}) {{\n")
        wrcpp(
            f" /* {t} */\n "
            "#ifdef DEBUG_PRINTS\n"
            f' std::cerr << "  -- {lvar} = {symbol[0]}; {rvar} = {symbol[1]} -->\\n";\n'
            "#endif /* !DEBUG_PRINTS */\n"
        )
        # wrcpp(f" if (ev2->{rvar} == {symbol[1]}) {{\n")
        wrcpp(
            f"   matched = true;\n "
            f"   _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1, cfg.p2 + 1);\n "
        )
        wrcpp(
            "#ifdef DEBUG_PRINTS\n"
            f'   std::cerr << "    => new (" << _cfgs.back_new().state  << ", " <<  _cfgs.back_new().p1 << ", " <<  _cfgs.back_new().p2 << ")\\n";\n'
            "#endif /* !DEBUG_PRINTS */\n"
        )
        # wrcpp("}\n")
        wrcpp("}\n")

    def handle_epsilon_step(self, automaton, t, lvar, rvar, wrcpp):
        wrcpp(
            f" /* {t} */\n "
            "#ifdef DEBUG_PRINTS\n"
            f' std::cerr << "  -- {lvar} = {t.label.symbol[0]}; {rvar} = {t.label.symbol[1]} -->\\n";\n'
            "#endif /* !DEBUG_PRINTS */\n"
        )
        l_automaton_registers = automaton.origin()[0].registers() or ()
        reg_substitution = [
            (r, Reg(f"cfg.{r.c_name()}.{lvar if r in l_automaton_registers else rvar}"))
            for r in automaton.registers()
        ]
        cond = condition_code(t, reg_substitution)
        wrcpp(f'/* COND: "{cond}"*/\n')
        if cond == "false":
            wrcpp("/* CONDITION UNSAT */")
        elif cond != "true":
            wrcpp(f"if ({cond}) ")
        wrcpp("{")
        dump_codegen_position(wrcpp)
        wrcpp(f"   matched = true;\n ")
        wrcpp(
            f"   _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1, cfg.p2);\n "
        )
        wrcpp(
            "#ifdef DEBUG_PRINTS\n"
            f'   std::cerr << "    => new (" << _cfgs.back_new().state  << ", " <<  _cfgs.back_new().p1 << ", " <<  _cfgs.back_new().p2 << ")\\n";\n'
            "#endif /* !DEBUG_PRINTS */\n"
        )
        wrcpp("}")

    def generate_atomic_comparison_automaton(self, bddnode: BDDNode):
        assert isinstance(bddnode, BDDNode), bddnode
        assert bddnode.automaton is None

        formula = bddnode.formula
        num = bddnode.get_id()
        nformula = formula
        # nformula = formula.rename_variables("v", "v", "t", "t")
        # we rename both projections to `v(t)` so that when we have another atom
        # that is the same but names of the trace variables, we do not rebuild it
        # A = self._automata.get(nformula)
        # if A:
        #   print(
        #       f"Duplicate atom for {formula }, re-using the automaton for {nformula}"
        #   )
        #   bddnode.automaton = Ap

        #   if self.args.debug:
        #       with self.new_dbg_file(f"aut-{num}.dot") as f:
        #           A.to_dot(f)
        #   return A

        A1 = self._automata.get(nformula.children[0])
        if A1 is None:
            A1 = formula_to_transducer(nformula.children[0])
            self._automata[nformula.children[0]] = A1
        else:
            print(f"Hit cache for {nformula.children[0]}")
        A2 = self._automata.get(nformula.children[1])
        if A2 is None:
            A2 = formula_to_transducer(nformula.children[1])
            self._automata[nformula.children[1]] = A2
        else:
            print(f"Hit cache for {nformula.children[1]}")

        # NOTE: we do not cache this one
        A = automaton_for_prefixing(A1, A2)
        # Ap = to_priority_automaton(A)

        A1.remove_redundant_states_once()
        A2.remove_redundant_states_once()

        if self.args.debug:
            with self.new_dbg_file(f"aut-{num}-lhs.dot") as f:
                A1.to_dot(f)
            with self.new_dbg_file(f"aut-{num}-rhs.dot") as f:
                A2.to_dot(f)
            with self.new_dbg_file(f"aut-{num}.dot") as f:
                A.to_dot(f)

        self._automata[nformula] = A

        assert len(A.accepting_states()) > 0, f"Automaton has no accepting states"
        assert len(A.initial_states()) > 0, f"Automaton has no initial states"

        return A

    def generate_tests(self):
        print("-- Generating tests --")
        makedirs(f"{self.out_dir}/tests", exist_ok=True)

        self.gen_config(
            "CMakeLists-atoms-tests.txt.in",
            "tests/CMakeLists.txt",
            {
                "@submonitors_libs@": " ".join(self._submonitors),
            },
        )

        print("FIXME: not generating tests")

    # for nd in self._bdd_nodes:
    #    num = nd.get_id()
    #    for test_num in range(0, 20):
    #        if test_num < 10:
    #            # make sure to generate some short tests
    #            path_len = random.randrange(0, 5)
    #        else:
    #            path_len = random.randrange(5, 100)

    #        path = random_path(nd.automaton, path_len)
    #        self.gen_test(nd.automaton, nd.formula, num, path, test_num)

    def gen_test(self, A, F, num, path, test_num):
        assert A.is_initial(path[0].source), "Path starts with non-initial state"
        is_accepting = path_is_accepting(A, path)
        lvar = F.children[0].program_variables()
        rvar = F.children[1].program_variables()
        assert len(lvar) <= 1, lvar
        assert len(rvar) <= 1, rvar
        if not (lvar or rvar):
            raise NotImplementedError("This case is unsupported yet")
        if not lvar:
            raise NotImplementedError("This case is unsupported yet")
        vars = (lvar[0].name if lvar else None, rvar[0].name if rvar else None)
        with self.new_file(f"tests/test-trace-{num}-{test_num}.cpp") as f:
            wr = f.write
            dump_codegen_position(f)
            wr(f"// The path used to generate this test:\n\n")
            for t in path:
                wr(f"// {t}\n")
            wr(f"// Accepting: {is_accepting}\n\n")
            dump_codegen_position(f)
            wr("Trace *trace1 = new Trace{1};\n")
            wr("Trace *trace2 = new Trace{2};\n\n")
            for i in range(0, 2):
                n = 0
                for t in path:
                    if t.label[i].is_epsilon():
                        continue
                    wr(f"trace{i+1}->append(Event{{ .{vars[i]} = {t.label[i]}}});\n")
                    n += 1
                wr(f"trace{i+1}->setFinished();")
                wr(f"/* Trace {i + 1} length: {n} */\n\n")

        self.gen_file(
            "test-atom.cpp.in",
            f"tests/test-atom-{num}-{test_num}.cpp",
            {
                "@TRACE@": f'#include "test-trace-{num}-{test_num}.cpp"',
                "@TRACE_VARIABLES@": ", ".join(
                    (f"trace{i+1}" for i, v in enumerate(vars) if v is not None)
                ),
                "@ATOM_NUM@": str(num),
                "@FORMULA@": str(F),
                "@MAX_TRACE_LEN@": str(len(path)),
                "@EXPECTED_VERDICT@": (
                    "Verdict::TRUE" if is_accepting else "Verdict::FALSE"
                ),
                "@namespace_using@": (
                    f"using namespace {self._namespace};" if self._namespace else ""
                ),
            },
        )

    def generate(self, formula, gen_tests=True):
        """
        The top-level method to generate code
        """

        self.generate_monitor(formula)
        if gen_tests:
            self.generate_tests()

        if self._embedded:
            from_dir = self.common_templates_path
            for f in ("atom-base.h", "atom-evaluation-state.h"):
                if f not in self.args.overwrite_file:
                    self.copy_file(f, from_dir=from_dir)
        else:
            self.copy_files()

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
        self.generate_cmake()

        self.format_generated_code()

    def generate_monitor(self, formula: PrenexFormula):
        assert not formula.has_quantifier_alternation(), formula
        input_traces = self._traces_attribute_str(formula)
        # NOTE: this method generates definitions of ctors and dtors into an .h file,
        # and returns a list of declarations of those ctors and dtors
        ctors_dtors = self._traces_ctors_dtors(formula, with_TS=False)
        inputs_finished = self._inputs_finished(formula)

        values = {
            "@monitor_name@": self.name(),
            "@namespace@": self.namespace(),
            "@namespace_start@": self.namespace_start(),
            "@namespace_end@": self.namespace_end(),
            "@input_traces@": input_traces,
            "@inputs_finished@": inputs_finished,
            "@ctors_dtors@": "\n".join(ctors_dtors),
            "@info@": f"Monitor for '{formula}'",
        }

        self.gen_file("hnl-atoms-monitor.h.in", "hnl-monitor.h", values)
        self.gen_file("hnl-atoms-monitor.cpp.in", "hnl-monitor.cpp", values)
        self.gen_file("atom-monitor.h.in", "atom-monitor.h", values)
        self.gen_file("finished-atom-monitor.h.in", "finished-atom-monitor.h", values)
        self.gen_file("regular-atom-monitor.h.in", "regular-atom-monitor.h", values)

        # there is no sub-formula, this is the monitor for the body of the formula
        self._gen_bdd_from_formula(formula)

        for nd in self._bdd_nodes:
            nd.automaton = self.generate_atomic_comparison_automaton(nd)

        # def gen_automaton(F):
        #    if not isinstance(F, IsPrefix):
        #        return

        # formula.visit(gen_automaton)

        self._generate_monitor(formula)
