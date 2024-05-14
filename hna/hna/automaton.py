from hna.automata.automaton import Automaton, State


class HypernodeState(State):
    def __init__(self, label, formula):
        super().__init__(label)
        self.formula = formula

    def dot_label(self):
        return f"{self.label()} | {self.formula}"


class HyperNodeAutomaton(Automaton):
    def __init__(self):
        super().__init__()
        self._actions = set()

    def actions(self):
        return self._actions

    def add_transition(self, t):
        self._actions.add(t.label)
        super().add_transition(t)
