from os import makedirs
from random import randrange

from rvhyno.automata.transducers import (
    Var,
    Reg,
    Value,
    TraceFinished,
    BinaryPredicate,
    Transition,
    Attr,
)
from rvhyno.codegen.utils import dump_codegen_position
from rvhyno.hnl.codegen.bdd import BDDNode, ConstBDDNode
from rvhyno.hnl.formula import (
    IsPrefix,
    PrenexFormula,
    Function,
    IsEq,
    TraceVariable,
    Comparison,
)
from .tests import path_is_accepting
from ..shared import CodeGenCppAtoms

from rvhyno.hnl.formula2transducers import Formula2Transducer, automaton_for_comparison

from rvhyno.utils import msg, log, args_str
from ..ehl import random_path


class TranslationData:
    def __init__(self, bddnode):
        self.automaton = bddnode.automaton
        # renamed trace variables
        renaming = bddnode.renaming
        # a list of traces to have a fixed order on them in the generated code
        # These are the original traces without renaming
        self.traces = sorted(
            list(t for t in self.automaton.traces if t not in renaming)
        )
        self.atom_formula = bddnode.formula
        self.num = bddnode.get_id()

        # if a trace appears in multiple projections, we have to keep track of
        # the position for each of the projections.
        # `traces_with_duplicates` will hold a list of all occurrences of trace variables,
        # renamed to be unique -- as a list of pairs (unique_name, original_name).
        tmp = {}
        ltraces, rtraces = [], []
        for t in (
            p.trace
            for p in self.atom_formula.children[0].program_variable_occurrences()
        ):
            ltraces.append((t, renaming.get(t, t)))
        for t in (
            p.trace
            for p in self.atom_formula.children[1].program_variable_occurrences()
        ):
            rtraces.append((t, renaming.get(t, t)))

        self.traces_with_duplicates = ltraces + rtraces
        self.ltraces = ltraces
        self.rtraces = rtraces

        self.renaming = renaming
        self.trace_to_ev = {
            t: Var(f"ev_{t.c_name()}") for t, _ in self.traces_with_duplicates
        }

    @property
    def events(self):
        return [self.trace_to_ev[tr] for tr in self.traces]

    def evs_pass_as_args(self) -> str:
        return args_str(
            ", ".join(
                (self.trace_to_ev[t].c_name() for t, _ in self.traces_with_duplicates)
            )
        )

    def evs_as_args(self) -> str:
        return args_str(
            ", ".join(
                (self._trace_to_ev_arg(t) for t, _ in self.traces_with_duplicates)
            )
        )

    def traces_as_args(self) -> str:
        return args_str(", ".join(f"Trace *{tr.c_name()}" for tr in self.traces))

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

    def _trace_to_ev_arg(self, t) -> str:
        return f"const Event *{self.trace_to_ev[t]}"


def subst_lst(c, lst):
    for s in lst:
        c = c.subst(s)
    return c


def rename_trace_variables(formula: Comparison):
    """
    Rename trace variables to be unique.
    Return a new formula with the renamed variables and a mapping
    of new names to old names.
    """
    # create a copy of the formula -- we will modify this copy
    formula = formula.substitute({})
    tmp = {}
    mapping = {}
    traces = [p.trace for p in formula.program_variable_occurrences()]
    for t in traces:
        # increase the counter of this trace
        n = tmp.setdefault(t, 0)
        n += 1
        tmp[t] = n

        if n > 1:
            new_name = f"{t.name}_{n}"
            mapping[TraceVariable(new_name)] = TraceVariable(t.name)
            # MODIFY the trace variable -- this way we modify only this
            # occurrence
            t.name = new_name
    return formula, mapping


def condition_code(t, data: TranslationData):
    # check that the traces read by these transitions have the events on them
    # (this is done by checking that the event variable for the transition is not nullptr)
    condition = [data.trace_to_ev[tr].c_code() for tr in t.label.symbols.keys()]
    subst = data.condition_substitutions(t) or []
    for cond in t.label.condition:
        if isinstance(cond, TraceFinished):
            condition.append(f"{data.trace_to_ev[cond.trace]} == nullptr")
            continue

        assert isinstance(cond, BinaryPredicate), cond

        # substitute variables for C code variables
        cond = subst_lst(cond, subst)
        lhs, rhs = cond.lhs, cond.rhs
        # we must still apply projection to registers
        if isinstance(lhs, Reg) and isinstance(rhs, Attr):
            cond.lhs = Attr(lhs, f"data.{rhs.attr}")
        if isinstance(rhs, Reg) and isinstance(lhs, Attr):
            cond.rhs = Attr(rhs, f"data.{lhs.attr}")

        condition.append(cond.c_code())

    c_cond = "&&".join(condition)
    if c_cond == "":
        return "true"
    return c_cond


def update_registers_code(t, data):
    update_registers = {}
    var_map = data.var_to_ev(t)
    for assign in t.label.assignment or ():
        assert isinstance(assign.to, Reg), assign
        assert isinstance(assign.val, Value), assign
        assert (
            assign.to not in update_registers
        ), f"A register updated multiple times: {t.label}"
        val = assign.val
        if isinstance(val, Attr):
            val = f"Register{{.type = RegisterType::{val.attr}, .data = {{.{val.attr} = {var_map[val.var]}->{val.attr}}}}}"
        else:
            val = f"Register{{.type = RegisterType::EVENT, .data = {{.EVENT = *{var_map[val.var].c_name()}}}}}"
        update_registers[assign.to] = val
    update_registers = [
        # default is to copy the old value
        update_registers.get(r, f"cfg.{r.c_name()}")
        for r in (data.automaton.registers() or ())
    ]
    return args_str(update_registers)


def are_independent(t1, t2):
    if t1.target != t2.target:
        return False

    l1, l2 = t1.label, t2.label
    # TODO: We could do better here
    if l1.assignment or l2.assignment:
        return False

    if set(l1.symbols.keys()).intersection(set(l2.symbols.keys())):
        return False

    return True


def compute_independent_transitions(transitions):
    """
    Get those transitions that are independent in the sense that
    they create the dimond in the state space: taking them one after another
    in any order leads to the same effect on the state.

    This function computes only transitions from one state, it means only self-loops.
    # FIXME: we also return just a single set of independent transitions of size 2,
    # but there could be more of them (sets and traces in the sets...)
    """
    T = {}
    for t in transitions:
        hit = False
        for cls in T.values():
            if are_independent(cls[0], t):
                cls.append(t)
                break
        if not hit:
            T[t] = [t]

    for cls in T.values():
        if len(cls) == 2:
            return cls

    return []


class CodeGenCpp(CodeGenCppAtoms):
    """
    The main class for generating C++ monitors for sHL.


    :param fixed_quantifiers:  assignment to quantifiers that stay fixed (do not change) in the monitor
                               generated by this codegen. That is, if `t1` is fixed in this monitor,
                               then it will refer to the same trace all the lifespan of the monitor
                               (while other quantifiers will get assigned different traces from the
                               trace sets).

    See the parent classes for other parameters' description.
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

    def _generate_registers(self):
        if "EVENT" in self.args.data:
            raise RuntimeError("A clash of names, an event cannot be called `EVENT`")

        self.gen_file("registers.h.in", "registers.h",
                      {'cg': self})
        self.gen_file("registers.cpp.in", "registers.cpp",
                      {'cg': self})
        self._generated_files.append("registers.cpp")

    def _generate_trivial_atom(self, nd):
        num, F = nd.get_id(), nd.formula

        if nd.bddvar.is_one():
            result = "Verdict::TRUE"
        elif nd.bddvar.is_zero():
            result = "Verdict::FALSE"
        else:
            raise NotImplementedError("Unknown BDD node")

        values = {
            "monitor_name": self.name(),
            "formula": str(nd.formula),
            "verdict": result,
            "atom_num": str(num),
        }

        self.gen_file("atoms/trivial-atom-monitor.h.in", f"atom-{num}.h", values)

    def _generate_automata_code(self, formula):
        # generated_automata = {}

        for nd in self._bdd_nodes:
            num, atom_formula = nd.get_id(), nd.formula
            log('dbg', "Generating code for automaton", nd.get_id(), ":", f'`{atom_formula}`', section=4)

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

            data = TranslationData(nd)

            # generate the CPP file
            with self.new_file(f"atom-{num}.cpp") as fcpp:
                self._generate_atom(data, formula, fcpp.write)
            self._atoms_files.append(f"atom-{num}.cpp")

            # generate the headers
            if nd.bddvar.is_zero() or nd.bddvar.is_one():
                self._generate_trivial_atom(nd)
                continue

            assert nd.automaton, f"{formula}"
            self._generate_atom_headers(data)

            # generated_automata[(nd.lvar, nd.rvar, nd.automaton.get_id())] = num

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


    def _generate_atom(self, data, formula: PrenexFormula, wrcpp):
        atom_formula, num, automaton = data.atom_formula, data.num, data.automaton

        # get traces from this formula. Strip off the function as its transducer has been composed into the automaton
        traces = [t.traces[0] if isinstance(t, Function) else t for t in data.traces]

        wrcpp(f'#include "atom-{num}.h"\n\n')
        if self._namespace:
            wrcpp(f"using namespace {self._namespace};\n\n")
        dump_codegen_position(wrcpp)

        traces_names = [t.name for t in traces]
        identifier = "AtomIdentifier{st"
        for q in formula.quantifiers():
            q_name = q.var.name
            if q_name in traces_names:
                identifier += f",instance.{q_name}->id()"
            else:
                identifier += ",0"
        identifier += "}"
        traces_args = args_str(", ".join(f"{t.c_name()}({t.c_name()})" for t in traces))
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const Instance& instance, FormulaEvaluationState st {data.traces_as_args().comma_prefixed()}) \n  :"
            f" RegularAtomMonitor({identifier}), {traces_args} {{\n\n"
        )
        if (
            automaton
        ):  # TRUE or FALSE nodes of BDD does not have an associated automaton
            assert (
                len(automaton.initial_states()) == 1
            ), f"Automaton {num} does not have exactly one initial states"

            registers = list(automaton.registers() or ())
            registers_defaults = args_str(("default_register" for _ in registers))

            initial_positions = args_str(
                ", ".join(str(0) for _ in data.traces_with_duplicates)
            )
            if registers:
                wrcpp("Register default_register;\n")

            wrcpp(
                f"_cfgs.emplace_back({automaton.get_state_id(automaton.initial_states()[0])} {initial_positions.comma_prefixed()} {registers_defaults.comma_prefixed()});\n"
            )
        wrcpp("}\n\n")

        instances_args = args_str(", ".join(f"instance.{t.c_name()}" for t in traces))
        identifier = f"AtomIdentifier{{ATOM_{num}"
        for q in formula.quantifiers():
            if q.var.name in traces_names:
                identifier += f",instance.{q.var.name}->id()"
            else:
                identifier += ",0"
        identifier += "}"
        dump_codegen_position(wrcpp)
        wrcpp(
            f"AtomMonitor{num}::AtomMonitor{num}(const Instance& instance) \n  : AtomMonitor{num}(instance, ATOM_{num} {instances_args.comma_prefixed()}) {{ }}\n\n"
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

        self.gen_handle_state(num, data, wrcpp)

        dump_codegen_position(wrcpp)
        wrcpp(
            "// FIXME: only modify configuration if it has a single possible successor\n"
        )

        wrcpp(
            f"void AtomMonitor{num}::_step(Atom{num}EvaluationState &cfg, {data.evs_as_args()}) {{\n"
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
                wrcpp("/* DROP CFG */\nbreak;\n\n")
                continue
            else:
                wrcpp(
                    f"stepState_{automaton.get_state_id(state)}(cfg, {data.evs_pass_as_args()});\n"
                )
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

        events_args = []
        for tr, tr_orig in data.traces_with_duplicates:
            ev = data.trace_to_ev[tr]
            wrcpp(
                f"""
                    Event {ev};
                    auto {ev}_status = {tr_orig.c_name()}->get(cfg.pos_{tr.c_name()}, {ev});
                    if ({ev}_status == TraceQuery::WAITING) {{
                        _cfgs.push_new(cfg);
                        continue;
                    }}
                """
            )
            events_args.append(
                f"{ev}_status == TraceQuery::END ? nullptr : &{ev.c_name()}"
            )
            # else:
            #     wrcpp("constexpr auto ev1ty = TraceQuery::END;")
            #
        debug_code_state(ns, data, wrcpp)

        self._check_accept(data, wrcpp)

        wrcpp(f"_step(cfg, {', '.join(events_args)});")
        wrcpp("}\n")

        wrcpp(f"_cfgs.rotate();")
        wrcpp(" return Verdict::UNKNOWN;\n")
        wrcpp("}\n\n")

    def _check_accept(self, data, wrcpp):
        dump_codegen_position(wrcpp)

        atom_formula = data.atom_formula
        if isinstance(atom_formula, IsEq):
            # all traces must be finished
            traces = data.traces_with_duplicates
        else:
            assert isinstance(atom_formula, IsPrefix), formula
            # only left traces must be finished
            traces = data.ltraces

        cond = " && ".join(
            f"{data.trace_to_ev[tr]}_status == TraceQuery::END" for tr, _ in traces
        )

        wrcpp(
            f"""
            /* FIXME: keep a track of ended traces (e.g., in a bitstring that would become 0
               once all traces are finished -- we would then check only for unfinished traces */
                 if (state_is_accepting(cfg.state)) {{
                     if ({cond}) {{
                         return Verdict::TRUE;
                     }}
                 }}
         """
        )

    def _generate_atom_headers(self, data):
        automaton = data.automaton
        num = data.num

        l_automaton_registers = automaton.origin()[0].registers() or ()
        registers = automaton.registers() or ()
        reg_types = "\n".join(f"using {r.c_name()}_t = Register;" for r in registers)
        reg_fields = "\n".join(
            f"Atom{num}EvaluationState::{r.c_name()}_t {r.c_name()};" for r in registers
        )

        position_args = args_str(
            ", ".join(
                f"unsigned pos_{tr.c_name()}" for tr, _ in data.traces_with_duplicates
            )
        )
        position_pass_args = args_str(
            ", ".join(f"pos_{tr.c_name()}" for tr, _ in data.traces_with_duplicates)
        )
        position_ctor = args_str(
            ", ".join(
                f"pos_{tr.c_name()}(pos_{tr.c_name()})"
                for tr, _ in data.traces_with_duplicates
            )
        )
        position_fields = "\n".join(
            f"unsigned pos_{tr.c_name()}{{0}};" for tr, _ in data.traces_with_duplicates
        )

        self.gen_file(
            "atoms/evaluation-state.h.in",
            f"atom-{num}-evaluation-state.h",
            {
                "cg": self,
                "monitor_name": self.name(),
                "atom_num": str(num),
                "position_args": position_args.comma_prefixed(),
                "position_pass_args": position_pass_args.comma_prefixed(),
                "position_fields": position_fields,
                "position_ctor": position_ctor.comma_prefixed(),
                "registers_types": reg_types,
                "registers_fields": reg_fields,
                "registers_args": args_str(
                    f"const Atom{num}EvaluationState::{r.c_name()}_t& {r.c_name()}"
                    for r in registers
                ).comma_prefixed(),
                "registers_pass_args": args_str(
                    r.c_name() for r in registers
                ).comma_prefixed(),
                "registers_ctor": args_str(
                    f"{r.c_name()}({r.c_name()})" for r in registers
                ).comma_prefixed(),
            },
        )

        with self.new_file(f"atom-{num}.h") as fh:
            self._generate_atom_header(data, fh.write)

    def _generate_atom_header(self, data, wrh):
        automaton, num = data.automaton, data.num

        self.gen_file("atoms/atom-shl.h.in", f"atom-{num}.h",
                      {'cg': self, 'num': num, 'automaton': automaton, 'data': data})

    def _generate_duplicate_atom(self, nd, duplicate_of, wrh, wrcpp):
        raise NotImplementedError("Not re-implemented for transducers")


    def gen_handle_state(self, aut_num, data, wrcpp):

        automaton = data.automaton
        for state in automaton.states():
            dump_codegen_position(wrcpp)
            wrcpp(
                f"void AtomMonitor{aut_num}::stepState_{automaton.get_state_id(state)}(Atom{aut_num}EvaluationState& cfg, {data.evs_as_args()}) {{\n"
            )

            self.gen_transitions_code(data, state, wrcpp)

            wrcpp("}\n\n ")

    def gen_transitions_code(self, data, state, wrcpp):
        transitions = data.automaton.transitions_from(state)

        T = compute_independent_transitions(transitions)
        if T:
            self.handle_indep_transitions(T[0], T[1], data, wrcpp)

        for tr in (t for t in transitions if t not in T):
            self.handle_transition(tr, data, wrcpp)

    def handle_transition(self, t: Transition, data: TranslationData, wrcpp) -> None:
        dump_codegen_position(wrcpp)

        cond = condition_code(t, data)
        wrcpp(f" if ({cond}) {{\n ")
        debug_code_transition_check(t, data, wrcpp)
        automaton = data.automaton
        update_registers = update_registers_code(t, data)
        progress_traces = t.label.symbols.keys()
        new_positions = args_str(
            ", ".join(
                (
                    f"cfg.pos_{tr.c_name()} + 1"
                    if tr in progress_traces
                    else f"cfg.pos_{tr.c_name()}"
                )
                for tr, _ in data.traces_with_duplicates
            )
        )
        wrcpp(
            f"  _cfgs.emplace_new({automaton.get_state_id(t.target)}, {new_positions} {update_registers.comma_prefixed()});\n "
        )
        debug_code_transition(wrcpp, data)
        # wrcpp("}\n")
        wrcpp("}\n")

    def handle_indep_transitions(
        self, t1: Transition, t2: Transition, data: TranslationData, wrcpp
    ) -> None:
        dump_codegen_position(wrcpp)

        automaton = data.automaton
        assert not t1.label.assignment
        assert not t2.label.assignment
        update_registers = update_registers_code(t1, data)
        cond1 = condition_code(t1, data)
        cond2 = condition_code(t2, data)

        wrcpp(f" if ({cond1}) {{\n ")
        debug_code_transition_check(t1, data, wrcpp)
        wrcpp(f" if ({cond2}) {{\n ")
        debug_code_transition_check(t2, data, wrcpp)
        progress_traces = list(t1.label.symbols.keys()) + list(t2.label.symbols.keys())
        new_positions = args_str(
            (
                f"cfg.pos_{tr.c_name()} + 1"
                if tr in progress_traces
                else f"cfg.pos_{tr.c_name()}"
            )
            for tr, _ in data.traces_with_duplicates
        )
        wrcpp(
            f"  _cfgs.emplace_new({automaton.get_state_id(t1.target)}, {new_positions} {update_registers.comma_prefixed()});\n "
        )
        debug_code_transition(wrcpp, data)
        wrcpp("} else {\n")
        # cond1 && ! cond2
        progress_traces = t1.label.symbols.keys()
        new_positions = args_str(
            (
                f"cfg.pos_{tr.c_name()} + 1"
                if tr in progress_traces
                else f"cfg.pos_{tr.c_name()}"
            )
            for tr, _ in data.traces_with_duplicates
        )
        wrcpp(
            f"  _cfgs.emplace_new({automaton.get_state_id(t1.target)}, {new_positions} {update_registers.comma_prefixed()});\n "
        )
        debug_code_transition(wrcpp, data)
        wrcpp("}\n")
        wrcpp("} else {\n")
        #! cond1
        wrcpp(f" if ({cond2}) {{\n ")
        debug_code_transition_check(t2, data, wrcpp)
        progress_traces = t2.label.symbols.keys()
        new_positions = args_str(
            (
                f"cfg.pos_{tr.c_name()} + 1"
                if tr in progress_traces
                else f"cfg.pos_{tr.c_name()}"
            )
            for tr, _ in data.traces_with_duplicates
        )
        wrcpp(
            f"  _cfgs.emplace_new({automaton.get_state_id(t2.target)}, {new_positions} {update_registers.comma_prefixed()});\n "
        )
        debug_code_transition(wrcpp, data)
        wrcpp("} \n")
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
        #
        if not formula.trace_variables():
            raise RuntimeError(
                f"No traces in the formula: '{formula}'. We do not support this case."
            )

        # FIXME: don't overwrite it like this, do it more clearly (e.g., before bulding BDD)
        nformula, renaming = rename_trace_variables(nformula)
        bddnode.formula = nformula

        A1 = self._automata.get(nformula.children[0])
        if A1 is None:
            A1 = Formula2Transducer(self.args.data_fun).formula_to_transducer(
                nformula.children[0]
            )
            self._automata[nformula.children[0]] = A1
        else:
            log('dbg', f"Hit cache for {nformula.children[0]}")
        A2 = self._automata.get(nformula.children[1])
        if A2 is None:
            A2 = Formula2Transducer(self.args.data_fun).formula_to_transducer(
                nformula.children[1]
            )
            self._automata[nformula.children[1]] = A2
        else:
            log('dbg', f"Hit cache for {nformula.children[1]}")

        A1 = A1.remove_redundant_states_once()
        A2 = A2.remove_redundant_states_once()

        A = automaton_for_comparison(
            A1, A2, aut_type="pref" if isinstance(nformula, IsPrefix) else "eq"
        )

        A = A.remove_redundant_states_once()

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

        return A, renaming

    def generate_tests(self):
        msg('info', "Generating tests", section=3)
        makedirs(f"{self._out_dir}/tests", exist_ok=True)

        self.gen_file(
            "atoms/CMakeLists-tests.txt.in",
            "tests/CMakeLists.txt",
            {
                "submonitors_libs": " ".join(self._submonitors),
            },
        )

        for nd in self._bdd_nodes:
           num = nd.get_id()
           for test_num in range(0, 20):
               if test_num < 10:
                   # make sure to generate some short tests
                   path_len = randrange(0, 5)
               else:
                   path_len = randrange(5, 100)

               path = random_path(nd.automaton, path_len)
               self.gen_test(nd.automaton, nd.formula, num, path, test_num)

    def gen_test(self, automaton, F, num, path, test_num):
        assert automaton.is_initial(path[0].source), "Path starts with non-initial state"
        is_accepting = path_is_accepting(automaton, path)
       # with self.new_file(f"tests/test-trace-{num}-{test_num}.cpp") as f:
       #     wr = f.write
       #     dump_codegen_position(f)
       #     wr(f"// The path used to generate this test:\n\n")
       #     for t in path:
       #         wr(f"// {t}\n")
       #     wr(f"// Accepting: {is_accepting}\n\n")
       #     dump_codegen_position(f)
       #     wr("Trace *trace1 = new Trace{1};\n")
       #     wr("Trace *trace2 = new Trace{2};\n\n")
       #     for i in range(0, 2):
       #         n = 0
       #         for t in path:
       #             if t.label.is_eps():
       #                 continue
       #             wr(f"trace{i+1}->append(Event{{ .{vars[i]} = {t.label}}});\n")
       #             n += 1
       #         dump_codegen_position(f)
       #         wr(f"trace{i+1}->setFinished();")
       #         wr(f"/* Trace {i + 1} length: {n} */\n\n")

        self.gen_file(
            "atoms/test-atom.cpp.in",
            f"tests/test-atom-{num}-{test_num}.cpp",
            {
                "cg": self,
                'automaton': automaton,
                'path': path,
                'is_accepting': is_accepting,
                "ATOM_NUM": str(num),
                "FORMULA": str(F)
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
            for f in ("atom-base.h",):
                if f not in self.args.overwrite_file:
                    self.copy_file(f, from_dir=from_dir)
        else:
            raise NotImplementedError("This should never be non-embedded in the current code")
            self.copy_files()

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

    def generate_monitor(self, formula: PrenexFormula):
        assert not formula.has_quantifier_alternation(), formula

        # there is no sub-formula, this is the monitor for the body of the formula
        msg('info', "Generating BDD for the formula", section=3)
        self._gen_bdd_from_formula(formula)

        msg('info', "Generating atomic comparison automata", section=3)
        for nd in self._bdd_nodes:
            # no automaton for this one, we'll handle that explicitly
            if isinstance(nd, ConstBDDNode):
                continue
            log('dbg', f"Generating atomic comparison automaton {nd.get_id()}", section=4)
            nd.automaton, nd.renaming = self.generate_atomic_comparison_automaton(nd)

        msg('info', "Generating monitor code", section=3)

        msg('info', "Generating BDD code", section=3)
        self._generate_bdd_code(formula)
        # Needed when generating formula-monitor.cpp
        self._generate_create_instances(formula)

        msg('info', "Generating stuctures for registers", section=3)
        self._generate_registers()
        msg('info', "Generating code for instances", section=3)
        self._generate_hnlinstances(formula)
        msg('info', "Generating automata for instances", section=3)
        self._generate_automata_code(formula)

        # NOTE: this code must come after _gen_bdd_from_formula as it uses the nodes
        values = {
            "cg": self,
            "monitor_name": self.name(),
            "formula": formula,
        }

        self.gen_file("atom-monitor.h.in", "atom-monitor.h", values)
        self.gen_file("atoms/formula-monitor.h.in", "formula-monitor.h", values)
        self.gen_file("atoms/formula-monitor.cpp.in", "formula-monitor.cpp", values)
        self.gen_file("atoms/finished-atom-monitor.h.in", "finished-atom-monitor.h", values)
        self.gen_file("atoms/regular-atom-monitor.h.in", "regular-atom-monitor.h", values)



def debug_code_state(ns, data, wrcpp):
    registers = data.automaton.registers() or ()
    reg = "<<".join(f'", " << "{r.c_name()}=" << cfg.{r.c_name()}' for r in registers)
    reg = reg + " << " if reg else ""
    ids = '<< ", " <<'.join(f"{tr.c_name()}->id()" for tr in data.traces)
    wrcpp(
        f"""
            #ifdef DEBUG_PRINTS
            std::cerr << "\033[0;36m{ns}Atom " << type() << " tr[" << {ids} << "] @ state " << cfg.state << {reg} ".\\n";
        """
    )

    for tr, _ in data.traces_with_duplicates:
        ev = data.trace_to_ev[tr]
        wrcpp(f'std::cerr << "\\n  {tr.c_name()}["<< cfg.pos_{tr.c_name()} <<"]: ";\n')
        wrcpp(
            f"""
                if ({ev}_status == TraceQuery::END) {{
                    std::cerr << "END";
                }} else {{
                    std::cerr << {ev};
                }}
            """
        )

    wrcpp(
        f"""
            std::cerr << "\033[0m\\n";
            #endif /* !DEBUG_PRINTS */
        """
    )


def debug_code_transition(wrcpp, data):
    r_str = "<<".join(
        f'", " << "{r.c_name()}=" << n_cfg.{r.c_name()}'
        for r in (data.automaton.registers() or ())
    )
    r_str = r_str + " << " if r_str else ""
    new_positions = '<< ", " <<'.join(
        f"n_cfg.pos_{tr.c_name()}" for tr, _ in data.traces_with_duplicates
    )
    wrcpp(
        "#ifdef DEBUG_PRINTS\n"
        "    const auto& n_cfg = _cfgs.back_new();\n"
        f'   std::cerr << "\033[0;32m    => next (state " << n_cfg.state  << ", [" << {new_positions} << "]" << {r_str} ")\033[0m\\n";\n'
        "#endif /* !DEBUG_PRINTS */\n"
    )


def debug_code_transition_check(t, data, wrcpp):
    out = f" [{', '.join(map(str, t.label.condition))}]" if t.label.condition else ""
    assignm = ", ".join(map(str, t.label.assignment or ()))
    symbols = ", ".join(f"{t}: {x}" for t, x in t.label.symbols.items())
    wrcpp(
        f" /* {t} */\n "
        "#ifdef DEBUG_PRINTS\n"
        f' std::cerr << "  -- \033[0;0m({symbols})\033[0m{out} ; {assignm} -->\\n";\n'
        "#endif /* !DEBUG_PRINTS */\n"
    )
