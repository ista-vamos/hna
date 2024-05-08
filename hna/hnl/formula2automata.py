from itertools import chain

from hna.automata.automaton import Automaton, State, Transition
from .formula import EPSILON, Constant, EPSILON_CONSTANT


def formula_to_automaton(formula, alphabet=None):
    A = Automaton(origin=formula)

    alphabet = alphabet or formula.constants()
    new_states = {formula}
    A.add_state(State(formula))
    if formula.nullable():
        A.add_accepting(A[formula])

    while new_states:
        state = new_states.pop()
        assert A.get(state) is not None

        for a in chain(
            alphabet,
            map(lambda x: x.with_rep(), alphabet),
            map(lambda x: x.with_x(), alphabet),
            map(lambda x: x.with_rep_x(), alphabet),
        ):
            for next_state in state.derivative(a):
                if A.get(next_state) is None:
                    s = State(next_state)
                    A.add_state(s)
                    if next_state.nullable():
                        A.add_accepting(s)
                    new_states.add(next_state)

                A.add_transition(Transition(A[state], a, A[next_state]))

    init = A[formula]
    A.add_init(init)
    if formula.nullable():
        A.add_accepting(init)

    return A


class TupleLabel(tuple):
    def __init__(self, args):
        super().__init__()

    def __str__(self):
        return f"{' ; '.join(map(str, self))}"


def gen_letter_pairs(alphabet):
    for a in alphabet:
        for marks1 in Constant.marks_combinations():
            for marks2 in Constant.marks_combinations():
                yield a.with_marks(marks1), a.with_marks(marks2)


def compose_automata(A1, A2, alphabet, prune=True):
    """
    Compose automata so that they recognize when inputs
    are in the prefixing relation.
    """

    A = Automaton(origin=(A1, A2))
    new_states = set()
    for i1 in A1.initial_states():
        for i2 in A2.initial_states():
            # prune surely non-accepting states
            if prune and i2.label() == EPSILON and not i1.nullable():
                continue
            new_states.add((i1.label(), i2.label()))
            state = State(TupleLabel((i1.label(), i2.label())))
            A.add_state(state)
            A.add_init(state)

    while new_states:
        state = new_states.pop()
        assert A.get(state) is not None

        ns1, ns2 = state
        ns1, ns2 = A1[ns1], A2[ns2]
        for a, a2 in gen_letter_pairs(alphabet):
            for t1 in A1.transitions(ns1, a, default=()):
                for t2 in A2.transitions(ns2, a2, default=()):
                    next_state = (t1.target.label(), t2.target.label())
                    # prune surely non-accepting states
                    if (
                        prune
                        and next_state[1] == EPSILON
                        and not next_state[0].nullable()
                    ):
                        continue
                    if A.get(next_state) is None:
                        s = State(TupleLabel(next_state))
                        A.add_state(s)
                        if next_state[0].nullable():
                            A.add_accepting(s)
                        new_states.add(next_state)

                    A.add_transition(
                        Transition(A[state], TupleLabel((a, a2)), A[next_state])
                    )

    return A


def to_priority_automaton(A: Automaton) -> Automaton:
    """
    Convert an automaton *over two input traces* to an
    automaton over two input traces with priorities on
    the edges.
    """
    states = set()
    O = Automaton(origin=A)

    for t in A.transitions():
        print(t)
        for s in (t.source, t.target):
            if s not in states:
                O.add_state(s)
                states.add(s)
                if A.is_initial(s):
                    O.add_init(s)
                if A.is_accepting(s):
                    O.add_accepting(s)

        label = t.label
        # replace non-x letters in label with epsilon
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

            source_label = t.source.label()
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

            source_label = t.source.label()
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
            source_label = t.source.label()
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
