import random
import re
from os import makedirs

from hna.automata.automaton import Automaton
from hna.automata.transducers import Var, Reg, Value, Eps, TraceFinished, Transition
from hna.codegen_common.utils import dump_codegen_position
from hna.hnl.codegen.bdd import BDDNode, ConstBDDNode
from hna.hnl.formula import IsPrefix, PrenexFormula, Function, TrivialTrue, IsEq
from hna.hnl.formula2automata import (
    formula_to_automaton,
    compose_automata,
    to_priority_automaton,
)
from .atoms import CodeGenCppAtoms
from ...formula2transducers import Formula2Transducer, automaton_for_comparison


class TranslationData:
    def __init__(self, automaton, atom_formula):
        self.automaton = automaton
        self.trace_to_ev = {t: Var(f"ev_{t.c_name()}") for t in automaton.traces}
        self.atom_formula = atom_formula

    def trace_to_ev_arg(self, t) -> str:
        return f"const Event *{self.trace_to_ev[t]}"

    def ev_as_args(self) -> str:
        return ", ".join((self.trace_to_ev_arg(t) for t in self.automaton.traces))

    def var_to_ev(self, transition) -> dict:
        # map variables of a transition to event pointers in the generated code
        return {
            symbol: self.trace_to_ev[tr]
            for tr, symbol in transition.label.symbols.items()
        }

    def condition_substitutions(self, t: Transition) -> list:
        substitution = [
            (r, Reg(f"(&cfg.{r.c_name()})")) for r in self.automaton.registers() or ()
        ]

        # map event variables to names of events in the code
        for tr, x in t.label.symbols.items():
            substitution.append((x, self.trace_to_ev[tr]))

        return substitution


class args_str(str):
    """
    A string representing arguments of a function/method.
    It can be built from an iterable, and it has some convenient methods.
    """

    def __new__(cls, string_or_iterable):
        if not isinstance(string_or_iterable, str):
            string_or_iterable = ", ".join(string_or_iterable)
        return super().__new__(cls, string_or_iterable)

    def comma_prefixed(self):
        return f", {self}" if self else ""


def subst_lst(c, lst):
    for s in lst:
        c = c.subst(s)
    return c


def condition_code(t, data: TranslationData):
    _cond = t.label.condition
    finished_cond = []
    # check that the traces read by this transitions have the events on them
    # (this is done by checking that the event variable for the transition is not nullptr)
    cond = [data.trace_to_ev[tr] for tr in t.label.symbols.keys()]
    for c in _cond:
        finished_cond.append(c) if isinstance(c, TraceFinished) else cond.append(c)

    subst = data.condition_substitutions(t)
    print(subst)
    if subst:
        cond = [subst_lst(c, subst or []).c_code() for c in cond]
    else:
        cond = [c.c_code() for c in cond]

    # The pointer to event is nullptr for traces that finished
    cond.extend((f"{data.trace_to_ev[c.trace]} == nullptr" for c in finished_cond))

    c_cond = "&&".join(cond)
    if c_cond == "":
        return "true"
    return c_cond


def update_registers_code(t, data):
    update_registers = {}
    var_map = data.var_to_ev
    for assign in t.label.assignment or ():
        assert isinstance(assign.to, Reg), assign
        assert isinstance(assign.val, Value), assign
        assert (
            assign.to not in update_registers
        ), f"A register updated multiple times: {t.label}"
        update_registers[assign.to] = var_map.get(assign.val, assign.val.c_name())
    update_registers = [
        update_registers.get(r, f"&cfg.{r.c_name()}")
        for r in (data.automaton.registers() or ())
    ]
    return args_str(update_registers)


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

    def _generate_trivial_atom(self, nd):
        num, F = nd.get_id(), nd.formula

        if nd.bddvar.is_one():
            result = "Verdict::TRUE"
        elif nd.bddvar.is_zero():
            result = "Verdict::FALSE"
        else:
            raise NotImplementedError("Unknown BDD node")

        values = {
            "@monitor_name@": self.name(),
            "@namespace@": self.namespace(),
            "@namespace_start@": self.namespace_start(),
            "@namespace_end@": self.namespace_end(),
            # "@info@": f"Monitor for '{nd.formula}'",
            "@formula@": str(nd.formula),
            "@verdict@": result,
            "@atom_num@": str(num),
        }

        self.gen_file("atom-trivial.h.in", f"atom-{num}.h", values)

    def _generate_automata_code(self, formula):
        generated_automata = {}
        for nd in self._bdd_nodes:
            num, F = nd.get_id(), nd.formula
            print("Generating code for", nd.get_id(), ":", F)

            # check duplicate atoms
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

            # generate the CPP file
            with self.new_file(f"atom-{num}.cpp") as fcpp:
                self._generate_atom(fcpp.write, formula, nd)
            self._atoms_files.append(f"atom-{num}.cpp")

            # generate the headers
            if nd.bddvar.is_zero() or nd.bddvar.is_one():
                self._generate_trivial_atom(nd)
                continue

            assert nd.automaton, f"{formula}"
            self._generate_atom_headers(F, nd, num)

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

        t1 = nd.ltrace or None
        t2 = nd.rtrace or None
        if not (nd.bddvar.is_zero() or nd.bddvar.is_one()):
            if not (t1 or t2):
                raise NotImplementedError("This case is unsupported yet")
            if not t1:
                raise NotImplementedError("This case is unsupported yet")

        if t1 and isinstance(t1, Function):
            # just strip off the function as its transducer has been composed into the automaton
            assert len(t1.traces) == 1
            t1 = t1.traces[0]
        if t2 and isinstance(t2, Function):
            assert len(t2.traces) == 1
            t2 = t2.traces[0]

        wrcpp(f'#include "atom-{num}.h"\n\n')
        if self._namespace:
            wrcpp(f"using namespace {self._namespace};\n\n")
        dump_codegen_position(wrcpp)

        identifier = "AtomIdentifier{st"
        for q in formula.quantifiers():
            if t1 and t2 and q.var.name in (t1.name, t2.name):
                identifier += f",instance.{q.var.name}->id()"
            else:
                identifier += ",0"
        identifier += "}"
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const Instance& instance, FormulaEvaluationState st, Trace *lt, Trace *rt) \n  :"
            f" RegularAtomMonitor({identifier}, lt, rt) {{\n\n"
        )
        if (
            automaton
        ):  # TRUE or FALSE nodes of BDD does not have an associated automaton
            assert (
                len(automaton.initial_states()) == 1
            ), f"Automaton {num} does not have exactly one initial states"

            # FIXME: this is a guess, we should properly use default constructors for register values...
            registers_defaults = args_str(
                ("&default_event" for _ in (automaton.registers() or ()))
            )
            wrcpp(
                "Event default_event;\n"
                f"_cfgs.emplace_back({automaton.get_state_id(automaton.initial_states()[0])}, 0, 0 {registers_defaults.comma_prefixed()});\n"
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
            f"AtomMonitor{num}::AtomMonitor{num}(const Instance& instance) \n  : AtomMonitor{num}(instance, ATOM_{num}, {t1_instance}, {t2_instance}) {{ }}\n\n"
        )

        if not automaton:
            # if this is the BDD node TRUE or FALSE,
            # we have generated all that we need (the ctors)
            return

        assert (
            len(automaton.initial_states()) == 1
        ), f"Automaton {num} does not have exactly one initial states"

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

        dump_codegen_position(wrcpp)
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

        debug_code_state(ns, t1, t2, wrcpp, automaton.registers() or ())

        dump_codegen_position(wrcpp)

        if isinstance(atom_formula, IsEq):
            wrcpp(
                f"""
                    if (ev1ty == TraceQuery::END && ev2ty == TraceQuery::END) {{
                        if (state_is_accepting(cfg.state)) {{
                            return Verdict::TRUE;
                        }}
                    }}
            """
            )
        else:
            assert isinstance(atom_formula, IsPrefix), formula
            assert t1 or t2
            evty = "ev1ty" if t1 else "ev2ty"

            wrcpp(
                f"""
                    if ({evty} == TraceQuery::END) {{
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

    def _generate_atom_headers(self, atom_formula, nd: BDDNode, num: int):
        automaton = nd.automaton
        lvar, rvar = nd.lvar, nd.rvar
        l_automaton_registers = automaton.origin()[0].registers() or ()
        registers = automaton.registers() or ()
        reg_types = "\n".join(f"using {r.c_name()}_t = Event;" for r in registers)
        reg_fields = "\n".join(
            f"Atom{num}EvaluationState::{r.c_name()}_t {r.c_name()};" for r in registers
        )
        self.gen_file(
            "atom-evaluation-state.h.in",
            f"atom-{num}-evaluation-state.h",
            {
                "@monitor_name@": self.name(),
                "@namespace@": self.namespace(),
                "@namespace_start@": self.namespace_start(),
                "@namespace_end@": self.namespace_end(),
                "@atom_num@": str(num),
                # "@registers_types@": f"{'\n'.join(f"using {r.c_name()}_t = decltype (Event().{lvar if r in l_automaton_registers else rvar});" for r in registers)}",
                "@registers_types@": reg_types,
                "@registers_fields@": reg_fields,
                "@registers_args@": args_str(
                    f"const Atom{num}EvaluationState::{r.c_name()}_t *{r.c_name()}"
                    for r in registers
                ).comma_prefixed(),
                "@registers_pass_args@": args_str(
                    r.c_name() for r in registers
                ).comma_prefixed(),
                "@registers_ctor@": args_str(
                    f"{r.c_name()}(*{r.c_name()})" for r in registers
                ).comma_prefixed(),
            },
        )

        with self.new_file(f"atom-{num}.h") as fh:
            self._generate_atom_header(atom_formula, automaton, num, fh.write)

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
        wrh(f'#include "atom-{num}-evaluation-state.h"\n\n')

        wrh(self.namespace_start())
        wrh("\n\n")

        dump_codegen_position(wrh)
        wrh(f"/* {atom_formula}*/\n")
        wrh(f"class AtomMonitor{num} : public RegularAtomMonitor {{\n\n")
        wrh(f" Atom{num}EvaluationStateSet _cfgs;\n\n")
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

        data = TranslationData(automaton, atom_formula)

        for state in automaton.states():
            dump_codegen_position(wrcpp)
            wrcpp(
                f"void AtomMonitor{aut_num}::stepState_{automaton.get_state_id(state)}(Atom{aut_num}EvaluationState& cfg, {data.ev_as_args()}) {{\n"
            )

            wrcpp(" bool matched = false;\n")

            self.gen_transitions_code(data, state, wrcpp)

            wrcpp("}\n\n ")

    def gen_transitions_code(self, data, state, wrcpp):
        transitions = data.automaton.transitions_from(state)

        for t in transitions:
            self.handle_transition(t, data, wrcpp)

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

    def handle_transition(self, t: Transition, data: TranslationData, wrcpp) -> None:
        dump_codegen_position(wrcpp)
        cond = condition_code(t, data)
        wrcpp(f" if ({cond}) {{\n ")
        debug_code_transition_check(t, data, wrcpp)
        # wrcpp(f" if (ev1->{lvar} == {symbol[0]} && ev2->{rvar} == {symbol[1]}) {{\n")
        automaton = data.automaton
        update_registers = update_registers_code(t, data)
        wrcpp(
            f"   matched = true;\n "
            f"  _cfgs.emplace_new({automaton.get_state_id(t.target)}, cfg.p1 + 1, cfg.p2 + 1 {update_registers.comma_prefixed()});\n "
        )
        debug_code_transition(wrcpp, automaton.registers() or ())
        # wrcpp("}\n")
        wrcpp("}\n")

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

        # `lvar = lvar or rvar` because if lvar is None,
        # then the comparison is between rvar and regular expressions, so
        # the traces of regular expression describe traces of rvar and
        # therefore `lvar or rvar` makes sense (because short-circuiting).
        # Similarly the symmetrical case
        rvar, lvar = bddnode.rvar, bddnode.lvar
        rvar = rvar or lvar
        lvar = lvar or rvar

        if not lvar and not rvar:
            raise RuntimeError(
                f"No traces in the formula: '{formula}'. We do not support this case."
            )

        A1 = self._automata.get(nformula.children[0])
        if A1 is None:
            A1 = Formula2Transducer(lvar, self.args.data_fun).formula_to_transducer(
                nformula.children[0]
            )
            self._automata[nformula.children[0]] = A1
        else:
            print(f"Hit cache for {nformula.children[0]}")
        A2 = self._automata.get(nformula.children[1])
        if A2 is None:
            A2 = Formula2Transducer(rvar, self.args.data_fun).formula_to_transducer(
                nformula.children[1]
            )
            self._automata[nformula.children[1]] = A2
        else:
            print(f"Hit cache for {nformula.children[1]}")

        A1.remove_redundant_states_once()
        A2.remove_redundant_states_once()

        A = automaton_for_comparison(
            A1, A2, aut_type="pref" if isinstance(nformula, IsPrefix) else "eq"
        )

        A.remove_redundant_states_once()

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
            for f in ("atom-base.h", "evaluation-state.h"):
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
        # values.update({"@include_headers@": '# include "atom-evaluation-state.h"'})
        self.gen_file("regular-atom-monitor.h.in", "regular-atom-monitor.h", values)

        # there is no sub-formula, this is the monitor for the body of the formula
        self._gen_bdd_from_formula(formula)

        for nd in self._bdd_nodes:
            # no automaton for this one, we'll handle that explicitly
            if isinstance(nd, ConstBDDNode):
                continue
            nd.automaton = self.generate_atomic_comparison_automaton(nd)

        # def gen_automaton(F):
        #    if not isinstance(F, IsPrefix):
        #        return

        # formula.visit(gen_automaton)

        self._generate_monitor(formula)


def debug_code_state(ns, t1, t2, wrcpp, registers):
    t1id = "t1->id()" if t1 else '"-"'
    t2id = "t2->id()" if t2 else '"-"'

    reg = "<<".join(f'", " << "{r.c_name()}=" << cfg.{r.c_name()}' for r in registers)
    reg = reg + " << " if reg else ""
    wrcpp(
        f"""
            #ifdef DEBUG_PRINTS
            std::cerr << "\033[0;36m{ns}Atom " << type() << " tr[" << {t1id} << ", " << {t2id} << "] @ state " << cfg.state << {reg} ".\\n";
            std::cerr << "  left[" << cfg.p1 << "] : ";
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

    wrcpp('std::cerr << "\\n  right["<< cfg.p2 <<"]: ";\n')

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
            std::cerr << "\033[0m\\n";
            #endif /* !DEBUG_PRINTS */
        """
    )


def debug_code_transition(wrcpp, registers):
    r_str = "<<".join(
        f'", " << "{r.c_name()}=" << n_cfg.{r.c_name()}' for r in registers
    )
    r_str = r_str + " << " if r_str else ""
    wrcpp(
        "#ifdef DEBUG_PRINTS\n"
        "    const auto& n_cfg = _cfgs.back_new();\n"
        f'   std::cerr << "\033[0;32m    => next (state " << n_cfg.state  << ", left[" << n_cfg.p1 << "], right[" << n_cfg.p2 << "]" << {r_str} ")\033[0m\\n";\n'
        "#endif /* !DEBUG_PRINTS */\n"
    )


def debug_code_transition_check(t, data, wrcpp):
    out = f" [{', '.join(map(str, t.label.condition))}]" if t.label.condition else ""
    assignm = ", ".join(map(str, t.label.assignment or ()))
    wrcpp(
        f" /* {t} */\n "
        "#ifdef DEBUG_PRINTS\n"
        # f' std::cerr << "  -- {lvar}(left) = {symbol[0]}; {rvar}(right) = {symbol[1]} -->\\n";\n'
        f' std::cerr << "  -- \033[0;0m{t.label.symbols}\033[0m{out} ; {assignm} -->\\n";\n'
        "#endif /* !DEBUG_PRINTS */\n"
    )
