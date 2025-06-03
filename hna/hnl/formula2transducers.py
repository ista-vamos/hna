from copy import copy

from .formula import (
    Constant as FormulaConstant,
    IsPrefix,
    StutterReduce,
    Concat,
    Iter,
    ProgramVariable,
    Function,
    Plus,
)
from .formula2automata import TupleLabel
from ..automata.transducers import (
    SymbolicTransducer,
    concat_transducers,
    Constant,
    Attr,
    Eps,
    iterate_transducer,
    union_transducers,
    Var,
    TransitionMultiLabel,
    TraceFinished,
    compose_transducers,
    Reg,
    Assignment,
    Eq,
    NEq,
    simplify_condition,
)
from ..automata.transition_system import State, Transition


def constant_transducer(formula):
    states = [State(f"c0"), State("c1")]
    x = Var("x")
    return SymbolicTransducer(
        states=states,
        registers=None,
        transitions=[
            Transition(
                states[0],
                TransitionMultiLabel({}, [], [], Constant(formula.value)),
                states[1],
            )
        ],
        init_states=[states[0]],
        accepting_states=[states[1]],
        origin=formula,
    )


def trace_transducer(trace):
    states = [State("v0"), State("vf")]
    return SymbolicTransducer(
        states=states,
        registers=None,
        transitions=[
            Transition(
                states[0],
                TransitionMultiLabel({trace: Var("x")}, [], [], Var("x")),
                states[0],
            ),
            Transition(
                states[0],
                TransitionMultiLabel({}, [TraceFinished(trace)], [], Eps()),
                states[1],
            ),
        ],
        init_states=[states[0]],
        accepting_states=[states[1]],
        origin=trace,
    )


class Formula2Transducer:
    def __init__(self, proj, data_funs=()):
        self._proj = proj
        self._data_funs = data_funs

    def formula_to_transducer(self, formula):
        """Return a transducer for a given formula that describes values of a projection `proj` of the trace"""
        assert not isinstance(formula, IsPrefix), formula

        if isinstance(formula, StutterReduce):
            return self.stutter_reduce_transducer(
                self.formula_to_transducer(formula.children[0]), formula
            )

        if isinstance(formula, Concat):
            return concat_transducers(
                self.formula_to_transducer(formula.children[0]),
                self.formula_to_transducer(formula.children[1]),
            )

        if isinstance(formula, Iter):
            return iterate_transducer(self.formula_to_transducer(formula.children[0]))

        if isinstance(formula, Plus):
            return union_transducers(
                self.formula_to_transducer(formula.children[0]),
                self.formula_to_transducer(formula.children[1]),
            )

        if isinstance(formula, FormulaConstant):
            return constant_transducer(formula)

        if isinstance(formula, ProgramVariable):
            if isinstance(formula.trace, Function):
                return self.projection_transducer(formula)
            return trace_transducer(formula.trace)

        raise NotImplementedError(f"Unhandled formula: {formula}")

    def stutter_reduce_transducer(self, T: SymbolicTransducer, formula):
        states = [State("st0"), State("st1")]
        r, x = Reg("last"), Var("x")
        proj = self._proj
        ST = SymbolicTransducer(
            states=states,
            registers=[r],
            transitions=[
                Transition(
                    states[0], TransitionLabel(x, [], [Assignment(r, x)], x), states[1]
                ),
                Transition(
                    states[1],
                    TransitionLabel(x, [Eq(Attr(x, proj), Attr(r, proj))], [], Eps()),
                    states[1],
                ),
                Transition(
                    states[1],
                    TransitionLabel(
                        x, [NEq(Attr(x, proj), Attr(r, proj))], [Assignment(r, x)], x
                    ),
                    states[1],
                ),
            ],
            init_states=[states[0]],
            accepting_states=states,
            origin=formula,
        )
        return compose_transducers(T, ST, origin=formula)

    def projection_transducer(self, formula):
        fn = formula.trace
        assert isinstance(fn, Function), formula
        if fn.name not in self._data_funs:
            raise RuntimeError(f"Unknown data function: {fn}")

        if len(fn.traces) != 1:
            raise RuntimeError("Multiple input traces to data function")

        fun_T = self._data_funs[fn.name]
        return compose_transducers(
            trace_transducer(fn.traces[0]), fun_T, origin=formula
        )


def compose_transitions(left_t, right_t, reg_map):
    label_l, label_r = left_t.label, right_t.label
    output_r = reg_map.get(label_r.output, label_r.output)
    symbols_l, symbols_r = label_l.symbols, label_r.symbols
    # the symbols on transitions are the same variable. We must rename one of them
    # (we rename the right one, since we are renaming also the right registers)
    new_r = {}
    cond_r = []
    assign_r = []
    symbols_l_values = symbols_l.values()
    for t, x in symbols_r.items():
        if x in symbols_l_values:
            newsym = copy(x)
            newsym.value = f"{x.value}'"
            subst = {x: newsym}
            new_r[t] = newsym
            cond_r = rename(label_r.condition, subst)
            assign_r = rename(label_r.assignment or [], subst)
            output_r = subst.get(output_r, output_r)
        else:
            new_r[t] = x
            cond_r = label_r.condition or []
            assign_r = label_r.assignment or []
    symbols_r = new_r
    output_l = label_l.output
    # lhs = output_l if isinstance(output_l, Constant) else Attr(output_l, lproj)
    # rhs = output_r if isinstance(output_r, Constant) else Attr(output_r, rproj)
    cond = simplify_condition(
        label_l.condition + rename(cond_r, reg_map) + [Eq(output_l, output_r)]
    )
    if cond is None:
        # the condition is UNSAT
        return None

    assign = ((label_l.assignment or []) + rename(assign_r, reg_map)) or None
    symbols = dict(symbols_l)
    symbols.update(symbols_r)
    return (
        (left_t.source, right_t.source),
        TransitionMultiLabel(symbols, cond, assign, Eps()),
        (left_t.target, right_t.target),
    )


def rename_lst(x, subst_lst: list):
    for s in subst_lst:
        x = x.subst(s)
    return x


def rename(lst, subst_map):
    if lst is None:
        return None

    return [rename_lst(x, subst_map.items()) for x in lst]


def automaton_for_comparison(
    left: SymbolicTransducer, right: SymbolicTransducer, aut_type: str
) -> SymbolicTransducer:
    """
    Compute the symbolic register automaton that accepts inputs of two transducers (left and right)
    such that the output of `left` is a prefix of (equal to) the output of `right`.
    We do not have a class for automata with registers, so we return a symbolic transducer
    that has no output.
    """

    # Pairs of states that we will later translate to State. But for now, it is more comfortable
    # to work with pairs of states.
    states = set()
    # triple (source, label, target) where source and target are pairs of states.
    # We will later translate them into Transition classes
    transitions = []
    queue = [
        TupleLabel((ii, oi))
        for ii in left.initial_states()
        for oi in right.initial_states()
    ]
    new_queue = []

    renamed_registers = {}
    registers = left.registers()
    registers = registers.copy() if registers else []
    for r in right.registers() or ():
        if r in registers:
            renamed_registers[r] = Reg(f"{r.value}_2")
            r = renamed_registers[r]
        registers.append(r)

    while queue:
        for state_pair in queue:
            if state_pair in states:
                continue
            states.add(state_pair)

            # case when the left transition outputs epsilon
            # In this case the right automaton does not move,
            # only the left one.
            for left_t in left.transitions_from(state_pair[0]):
                left_l = left_t.label
                if left_l.is_output_eps():
                    new_target = (left_t.target, state_pair[1])
                    transitions.append(
                        (
                            state_pair,
                            TransitionMultiLabel(
                                left_l.symbols,
                                left_l.condition,
                                left_l.assignment,
                                Eps(),
                            ),
                            new_target,
                        )
                    )
                    new_queue.append(new_target)

            # case when the right transition outputs epsilon
            for right_t in right.transitions_from(state_pair[1]):
                # handle epsilon steps of outer transducer
                right_l = right_t.label
                if right_l.is_output_eps():
                    new_target = (state_pair[0], right_t.target)
                    transitions.append(
                        (
                            state_pair,
                            TransitionMultiLabel(
                                right_l.symbols,
                                rename(right_l.condition, renamed_registers),
                                rename(right_l.assignment, renamed_registers),
                                Eps(),
                            ),
                            new_target,
                        )
                    )
                    new_queue.append(new_target)

            # case when both transitions output something
            for left_t, right_t in (
                (lt, rt)
                for lt in left.transitions_from(state_pair[0])
                for rt in right.transitions_from(state_pair[1])
            ):
                print("##", left_t, "##", right_t)
                if right_t.label.is_output_eps() or left_t.label.is_output_eps():
                    # these were handled separately
                    print("  skip")
                    continue

                # combine the transitions
                new_t = compose_transitions(left_t, right_t, renamed_registers)
                if new_t is None:
                    # the transition had UNSAT condition
                    continue
                assert new_t[0] == state_pair
                assert new_t[0] == (left_t.source, right_t.source)
                assert new_t[2] == (left_t.target, right_t.target)
                print(f"NEW_T: {new_t[0]} - {new_t[1]} -> {new_t[2]}")
                transitions.append(new_t)
                # new_t[2] is the target of the new to-be-transition
                if new_t[2] not in states:
                    new_queue.append(new_t[2])

        queue, new_queue = new_queue, []

    states = {(l, r): State(str(TupleLabel((l, r)))) for (l, r) in states}

    if aut_type == "pref":
        accepting_states = [states[s] for s in states.keys() if left.is_accepting(s[0])]
    elif aut_type == "eq":
        accepting_states = [
            states[s]
            for s in states.keys()
            if left.is_accepting(s[0]) and right.is_accepting(s[1])
        ]
    else:
        raise NotImplementedError("Unknown type of comparison")

    return SymbolicTransducer(
        states=list(states.values()),
        registers=registers or None,
        transitions=[Transition(states[t[0]], t[1], states[t[2]]) for t in transitions],
        init_states=[
            states[s]
            for s in states.keys()
            if left.is_initial(s[0]) and right.is_initial(s[1])
        ],
        accepting_states=accepting_states,
        origin=(left, right),
    )
