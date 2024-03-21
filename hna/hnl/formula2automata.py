from hna.automata.automaton import Automaton, State, Transition
from itertools import chain

from .formula import EPSILON, Constant


def formula_to_automaton(formula, alphabet=None):
    A = Automaton()

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


def compose_automata(A1, A2, prune=True):
    """
    Compose automata so that they recognize when inputs
    are in the prefixing relation.
    """
    A = Automaton()
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

    alphabet = set()
    for i in A1.initial_states():
        alphabet.update(i.label().constants())
    for i in A2.initial_states():
        alphabet.update(i.label().constants())

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
