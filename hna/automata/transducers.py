from hna.automata.transition_system import (
    State as TSState,
    Transition as TSTransition,
    TransitionSystem,
    AccInitTransitionSystem,
)


class Transition(TSTransition):
    def __init__(self, source, label, target, output, priority=0):
        super().__init__(source, label, target, priority)
        self._output = output

        # the transition does not change, precompute its str and hash,
        # because these are used a lot and we want them to be fast
        prio = f":{priority}" if self._priority != 0 else ""
        self._str = f"({source} -[{label}{prio}/{self._output}]-> {target})"
        self._hash = hash((source, target, label, priority))

    @property
    def output(self):
        return self._output

    def dot_label(self):
        return f"{self.label}/{self.output}"


class Transducer(AccInitTransitionSystem):
    """Class representing a finite-state transducer"""

    def __init__(
        self,
        states: list = None,
        transitions: list = None,
        init_states: list = None,
        acc_states: list = None,
        origin=None,
    ):
        super().__init__(states, transitions, init_states, acc_states, origin=origin)


class SymbolicTransducer(Transducer):
    """Symbolic finite-state transducer with registers"""

    def __init__(
        self,
        states: list = None,
        registers: list = None,
        transitions: list = None,
        init_states: list = None,
        accepting_states: list = None,
        origin=None,
    ):
        super().__init__(states, transitions, init_states, accepting_states, origin)
        self._registers = registers

    @property
    def registers(self):
        return self._registers
