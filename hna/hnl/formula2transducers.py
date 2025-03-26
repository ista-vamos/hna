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
)
from ..automata.transition_system import State, Transition


def constant_transducer(formula):
    states = [State("q0"), State("q1")]
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
    states = [State("q0")]
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
    return T


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


def to_priority_automaton(A: Automaton) -> Automaton:
    """
    Convert an automaton *over two input traces* to an
    automaton over two input traces with priorities on
    the edges.
    """
    assert False
    states = set()
    O = Automaton(origin=A)

    for t in A.transitions():
        for s in (t.source, t.target):
            if s not in states:
                O.add_state(s)
                states.add(s)
                if A.is_initial(s):
                    O.add_init(s)
                if A.is_accepting(s):
                    O.add_accepting(s)

        label = t.label
        # replace non-x letters in symbol with epsilon
        if not label[0].is_x():
            label = TupleLabel((EPSILON_CONSTANT, label[1]))
        if not label[1].is_x():
            label = TupleLabel((label[0], EPSILON_CONSTANT))

        l0, l1 = label[0].remove_x(), label[1].remove_x()

        if l0.is_rep() and l1.is_rep():
            # create the new middle state
            assert not l0.is_epsilon()
            assert not l1.is_epsilon()
            l0 = l0.remove_rep()
            l1 = l1.remove_rep()

            source_label = t.source.name()
            s = O.get_or_create_state(
                TupleLabel((source_label[0], source_label[1], l0, l1))
            )

            O.add_transition(Transition(t.source, TupleLabel((l0, l1)), s))
            O.add_transition(Transition(s, TupleLabel((l0, l1)), s, priority=2))
            O.add_transition(
                Transition(s, TupleLabel((l0, EPSILON_CONSTANT)), s, priority=1)
            )
            O.add_transition(
                Transition(s, TupleLabel((EPSILON_CONSTANT, l1)), s, priority=1)
            )
            O.add_transition(
                Transition(
                    s, TupleLabel((EPSILON_CONSTANT, EPSILON_CONSTANT)), t.target
                )
            )
        elif l0.is_rep():
            # create the new middle state
            assert not l0.is_epsilon()
            l0 = l0.remove_rep()

            source_label = t.source.name()
            s = O.get_or_create_state(
                TupleLabel((source_label[0], source_label[1], l0))
            )

            O.add_transition(Transition(t.source, TupleLabel((l0, l1)), s))
            O.add_transition(
                Transition(s, TupleLabel((l0, EPSILON_CONSTANT)), s, priority=1)
            )
            O.add_transition(
                Transition(
                    s, TupleLabel((EPSILON_CONSTANT, EPSILON_CONSTANT)), t.target
                )
            )
        elif l1.is_rep():
            assert not l1.is_epsilon()
            l1 = l1.remove_rep()

            # create the new middle state
            source_label = t.source.name()
            s = O.get_or_create_state(
                TupleLabel((source_label[0], source_label[1], l1))
            )

            O.add_transition(Transition(t.source, TupleLabel((l0, l1)), s))
            O.add_transition(
                Transition(s, TupleLabel((EPSILON_CONSTANT, l1)), s, priority=1)
            )
            O.add_transition(
                Transition(
                    s, TupleLabel((EPSILON_CONSTANT, EPSILON_CONSTANT)), t.target
                )
            )
        else:
            O.add_transition(Transition(t.source, TupleLabel((l0, l1)), t.target))

    return O
