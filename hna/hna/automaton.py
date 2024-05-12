from hna.automata.automaton import Automaton, State


class HypernodeState(State):
    def __init__(self, label, formula):
        super().__init__(label)
        self.formula = formula

    def dot_label(self):
        return f"{self.label()} | {self.formula}"


class HyperNodeAutomaton(Automaton):
    pass
