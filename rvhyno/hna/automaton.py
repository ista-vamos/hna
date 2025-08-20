from rvhyno.automata.automaton import Automaton
from rvhyno.automata.transition_system import State


class HypernodeState(State):
    def __init__(self, label, formula):
        super().__init__(label)
        self.formula = formula

    def dot_name(self):
        return f"{self.name()} | {self.formula}"


class HyperNodeAutomaton(Automaton):
    def __init__(self):
        super().__init__()
        self._actions = set()

    def actions(self):
        return self._actions

    def add_transition(self, t):
        self._actions.add(t.name)
        super().add_transition(t)
