from copy import copy

from hna.automata.automaton import Automaton
from .formula import (
    Constant,
    EPSILON_CONSTANT,
    IsPrefix,
    StutterReduce,
    Concat,
    Iter,
    ProgramVariable,
)
from ..automata.transducers import (
    SymbolicTransducer,
    concat_transducers,
    Constant as TransitionConstant,
    Eps,
    iterate_transducer,
    Var,
    TransitionLabel,
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
    return SymbolicTransducer(
        states=states,
        registers=None,
        transitions=[
            Transition(
                states[0],
                TransitionLabel(Eps(), [], [], TransitionConstant(formula.value)),
                states[1],
            )
        ],
        init_states=[states[0]],
        accepting_states=[states[1]],
        origin=formula,
    )


def program_variable_transducer(formula):
    states = [State("v0")]
    return SymbolicTransducer(
        states=states,
        registers=None,
        transitions=[
            Transition(
                states[0], TransitionLabel(Var("x"), [], [], Var("x")), states[0]
            )
        ],
        init_states=states,
        accepting_states=states,
        origin=formula,
    )


def stutter_reduce_transducer(T: SymbolicTransducer):
    states = [State("st0"), State("st1")]
    r, x = Reg("last"), Var("x")
    ST = SymbolicTransducer(
        states=states,
        registers=[r],
        transitions=[
            Transition(
                states[0], TransitionLabel(x, [], [Assignment(r, x)], x), states[1]
            ),
            Transition(states[1], TransitionLabel(x, [Eq(x, r)], [], Eps()), states[1]),
            Transition(
                states[1],
                TransitionLabel(x, [NEq(x, r)], [Assignment(r, x)], x),
                states[1],
            ),
        ],
        init_states=[states[0]],
        accepting_states=states,
    )
    return compose_transducers(T, ST)


def formula_to_transducer(formula):
    assert not isinstance(formula, IsPrefix), formula

    if isinstance(formula, StutterReduce):
        return stutter_reduce_transducer(formula_to_transducer(formula.children[0]))

    if isinstance(formula, Concat):
        return concat_transducers(
            formula_to_transducer(formula.children[0]),
            formula_to_transducer(formula.children[1]),
        )

    if isinstance(formula, Iter):
        return iterate_transducer(formula_to_transducer(formula.children[0]))

    if isinstance(formula, Constant):
        return constant_transducer(formula)

    if isinstance(formula, ProgramVariable):
        return program_variable_transducer(formula)

    raise NotImplementedError(f"Unhandled formula: {formula}")


from .formula2automata import TupleLabel


def compose_transitions(left_t, right_t, reg_map):
    label_l, label_r = left_t.label, right_t.label
    output_r = reg_map.get(label_r.output, label_r.output)
    symbol_r = label_r.symbol
    # the symbols on transitions are the same variable. We must rename one of them
    # (we rename the right one, since we are renaming also the right registers)
    if isinstance(symbol_r, Var) and symbol_r == label_l.symbol:
        sym = copy(symbol_r)
        sym.value = f"{symbol_r.value}'"
        subst = {symbol_r: sym}
        symbol_r = sym
        cond_r = rename(label_r.condition, subst)
        assign_r = rename(label_r.assignment or [], subst)
    else:
        cond_r = label_r.condition or []
        assign_r = label_r.assignment or []
    cond = simplify_condition(
        label_l.condition + rename(cond_r, reg_map) + [Eq(label_l.output, output_r)]
    )
    if cond is None:
        return None
    assign = ((label_l.assignment or []) + rename(assign_r, reg_map)) or None

    return (
        (left_t.source, right_t.source),
        TransitionLabel(TupleLabel((label_l.symbol, symbol_r)), cond, assign, Eps()),
        (left_t.target, right_t.target),
    )


def rename(lst, subst_map):
    print("RENAME: ", [str(x) for x in lst])
    if lst is None:
        return None
    return [x.subst(item) for x in lst for item in subst_map.items()]


def automaton_for_prefixing(
    left: SymbolicTransducer, right: SymbolicTransducer
) -> SymbolicTransducer:
    """
    Compute the symbolic register automaton that accepts inputs of two transducers (left and right)
    such that the output of 'left' is a prefix of 'right'.
    We do not have a class for automata with registers, so we return a symbolic transducer
    that has no output.
    """

    # pairs of states that we will later translate to State. But for now, it is more comfortable
    # to work with pairs of states.
    states = set()
    # triple (source, label, target) where source and target are pairs of states.
    # We will later translate them into Transition classes
    transitions = []
    queue = [(ii, oi) for ii in left.initial_states() for oi in right.initial_states()]
    new_queue = []

    renamed_registers = {}
    registers = left.registers().copy() if left.registers() else []
    for r in right.registers() or ():
        if r in registers:
            renamed_registers[r] = Reg(f"{r.value}_2")
            r = renamed_registers[r]
        registers.append(r)

    while queue:
        for state_pair in queue:
            print(f"CUR: {state_pair[0]},{state_pair[1]}")
            if state_pair in states:
                continue
            states.add(state_pair)

            # case when the left transition outputs epsilon
            for left_t in left.transitions_from(state_pair[0]):
                # handle epsilon steps of outer transducer
                left_l = left_t.label
                if left_l.is_output_eps():
                    new_target = (left_t.target, state_pair[1])
                    transitions.append(
                        (
                            state_pair,
                            TransitionLabel(
                                TupleLabel((left_l.symbol, Eps())),
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
                            TransitionLabel(
                                TupleLabel((Eps(), right_l.symbol)),
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
                print(
                    f"NEW_T: {new_t[0][0]},{new_t[0][1]} - {new_t[1]} -> {new_t[2][0]},{new_t[2][1]}"
                )
                transitions.append(new_t)
                # new_t[2] is the target of the new to-be-transition
                if new_t[2] not in states:
                    print(f"NEW: {new_t[2][0]}{new_t[2][1]}")
                    new_queue.append(new_t[2])

        queue, new_queue = new_queue, []

    states = {(l, r): State(f"{l} # {r}") for (l, r) in states}

    return SymbolicTransducer(
        states=list(states.values()),
        registers=registers or None,
        transitions=[Transition(states[t[0]], t[1], states[t[2]]) for t in transitions],
        init_states=[
            states[s]
            for s in states.keys()
            if left.is_initial(s[0]) and right.is_initial(s[1])
        ],
        accepting_states=[states[s] for s in states.keys() if left.is_accepting(s[0])],
        origin=(left, right),
    )
