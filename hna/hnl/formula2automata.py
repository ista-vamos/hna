from hna.automata.automaton import Automaton, State, Transition
from itertools import chain

from formula import RepConstant


def formula_to_automaton(formula):
    A = Automaton()

    alphabet = formula.constants()
    new_states = set((formula,))

    while new_states:
        state = new_states.pop()
        A.add_state(State(state))
        assert A.get(state) is not None

        for a in chain(alphabet, map(lambda x: RepConstant(x), alphabet)):
            for next_state in state.derivative(a):
                print("  d: ", next_state)
                if A.get(next_state) is None:
                    A.add_state(State(next_state))
                    new_states.add(next_state)

                A.add_transition(Transition(A[state], a, A[next_state]))

    return A
