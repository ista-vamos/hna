from copy import copy

from .formula import (
    Constant as FormulaConstant,
    IsPrefix,
    StutterReduce,
    Concat,
    Iter,
    ProgramVariable,
    TraceVariable,
    Plus,
    Slice,
    Lang,
)
from .formula2automata import TupleLabel
from ..automata.transducers import (
    SymbolicTransducer,
    concat_transducers,
    iterate_transducer,
    union_transducers,
    compose_transducers,
    substitute_trace,
)
from ..automata.transducers.labels import (
    TransitionMultiLabel,
    Constant,
    Attr,
    Eps,
    Var,
    TraceFinished,
    Reg,
    Assignment,
    Eq,
    NEq,
)
from ..automata.transducers.operations import simplify_condition, remove_epsilon_steps
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


def attr_transducer(trace, projection: str):
    states = [State("v0"), State("vf")]
    out = Var("x") if projection is None else Attr(Var("x"), projection)
    return SymbolicTransducer(
        states=states,
        registers=None,
        transitions=[
            Transition(
                states[0],
                TransitionMultiLabel({trace: Var("x")}, [], [], out),
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


def positive_slice_transducer(interval):
    # we need some dummy trace that serves as the input to the transducer
    trace = TraceVariable("𝜏")
    i, j = interval
    assert 0 <= i <= j
    states = [State("b0")]
    acc = []
    transitions = []
    # drop i - 1 letters from the word
    for n in range(1, i + 1):
        s1, s2 = states[-1], State(f"b{n}")
        states.append(s2)
        transitions.append(
            Transition(s1, TransitionMultiLabel({trace: Var("x")}, [], [], Eps()), s2)
        )
    # copy letters from i-th position to j-1th position
    for n in range(i + 1, j + 2):
        s1, s2 = states[-1], State(f"b{n}")
        states.append(s2)
        acc.append(s2)
        transitions.append(
            Transition(
                s1, TransitionMultiLabel({trace: Var("x")}, [], [], Var("x")), s2
            )
        )

    # drop the rest
    s = states[-1]
    transitions.append(
        Transition(s, TransitionMultiLabel({trace: Var("x")}, [], [], Eps()), s),
    )

    return SymbolicTransducer(
        states=states,
        registers=[],
        transitions=transitions,
        init_states=[states[0]],
        accepting_states=acc,
        origin=None,
    )


def last_elem_transducer():
    # we need some dummy trace that serves as the input to the transducer
    trace = TraceVariable("𝜏")
    states = [State("q0"), State("q1"), State("q2")]
    r, x = Reg("last"), Var("x")
    transitions = [
        Transition(
            states[0],
            TransitionMultiLabel({}, [TraceFinished(trace)], [], Eps()),
            states[2],
        ),
        Transition(
            states[0],
            TransitionMultiLabel({trace: x}, [], [Assignment(r, x)], Eps()),
            states[1],
        ),
        Transition(
            states[1],
            TransitionMultiLabel({trace: x}, [], [Assignment(r, x)], Eps()),
            states[1],
        ),
        Transition(
            states[1],
            TransitionMultiLabel({}, [TraceFinished(trace)], [], r),
            states[2],
        ),
    ]

    return SymbolicTransducer(
        states=states,
        registers=[r],
        transitions=transitions,
        init_states=[states[0]],
        accepting_states=[states[2]],
        origin=None,
    )


class Formula2Transducer:
    def __init__(self, data_funs=()):
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
            if formula.name in self._data_funs:
                return self.data_fun_transducer(formula)
            return attr_transducer(formula.trace, formula.name)

        if isinstance(formula, Slice):
            assert len(formula.children) == 1, formula
            return self.slice_transducer(
                self.formula_to_transducer(formula.children[0]), formula
            )

        if isinstance(formula, Lang):
            return self.data_fun_transducer(formula)

        raise NotImplementedError(f"Unhandled formula: {formula}")

    def stutter_reduce_transducer(self, T: SymbolicTransducer, formula):
        trace = TraceVariable("𝜏")
        states = [State("st0"), State("st1")]
        r, x = Reg("last"), Var("x")
        ST = SymbolicTransducer(
            states=states,
            registers=[r],
            transitions=[
                Transition(
                    states[0],
                    TransitionMultiLabel({trace: x}, [], [Assignment(r, x)], x),
                    states[1],
                ),
                Transition(
                    states[1],
                    TransitionMultiLabel({trace: x}, [Eq(x, r)], [], Eps()),
                    states[1],
                ),
                Transition(
                    states[1],
                    TransitionMultiLabel(
                        {trace: x}, [NEq(x, r)], [Assignment(r, x)], x
                    ),
                    states[1],
                ),
            ],
            init_states=[states[0]],
            accepting_states=states,
            origin=formula,
        )
        return compose_transducers(T, ST, on=trace, origin=formula)

    def slice_transducer(self, T: SymbolicTransducer, formula):
        interval = formula.interval
        if 0 <= interval[0] <= interval[1]:
            ST = positive_slice_transducer(interval)
        elif interval[0] == interval[1] == -1:
            ST = last_elem_transducer()
        else:
            raise NotImplementedError(f"This slicing is not implemented: {formula}")

        return compose_transducers(T, ST, ST.get_single_trace(), origin=formula)

    def data_fun_transducer(self, formula):
        fun = formula.name
        if fun not in self._data_funs:
            raise RuntimeError(f"Unknown data function: {fun}")

        T = self._data_funs[fun]

        if len(T.traces) == 0:
            assert isinstance(formula, Lang), formula
            # This is just a regular expression as an automaton
            return T

        if len(T.traces) > 1:
            raise RuntimeError(
                f"Data function transducer used in situation where it needs to have exactly one trace, "
                "but it has {len(T.traces)} traces."
            )
        return substitute_trace(T, next(iter(T.traces)), formula.trace)

    # return compose_transducers(
    #    attr_transducer(formula.trace, fun),
    #    fun_T,
    #    on=fun_T.get_single_trace(),
    #    origin=formula,
    # )


def compose_transitions(left_t, right_t, reg_map):
    label_l, label_r = left_t.label, right_t.label
    output_r = reg_map.get(label_r.output, label_r.output)
    symbols_l, symbols_r = label_l.symbols, label_r.symbols

    # Rename variables to be unique (we rename the right variables,
    # since we are renaming also the right registers)
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
            output_r = output_r.subst((x, newsym))
        else:
            new_r[t] = x
            cond_r = label_r.condition or []
            assign_r = label_r.assignment or []
    symbols_r = new_r
    output_l = label_l.output
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
                # print("##", left_t, "##", right_t)
                if right_t.label.is_output_eps() or left_t.label.is_output_eps():
                    # these were handled separately
                    continue

                # combine the transitions
                new_t = compose_transitions(left_t, right_t, renamed_registers)
                if new_t is None:
                    # the transition had UNSAT condition
                    continue
                assert new_t[0] == state_pair
                assert new_t[0] == (left_t.source, right_t.source)
                assert new_t[2] == (left_t.target, right_t.target)
                # print(f"NEW_T: {new_t[0]} - {new_t[1]} -> {new_t[2]}")
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

    return remove_epsilon_steps(
        SymbolicTransducer(
            states=list(states.values()),
            registers=registers or None,
            transitions=[
                Transition(states[t[0]], t[1], states[t[2]]) for t in transitions
            ],
            init_states=[
                states[s]
                for s in states.keys()
                if left.is_initial(s[0]) and right.is_initial(s[1])
            ],
            accepting_states=accepting_states,
            origin=(left, right),
        )
    )
