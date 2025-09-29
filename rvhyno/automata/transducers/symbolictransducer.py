from .labels import Reg

from rvhyno.automata.transition_system import AccInitTransitionSystem, Transition, State
from rvhyno.hnl.formula import TraceVariable


# FIXME: rename to MST (Multi-trace symbolic transducer)
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
    """Mutli-tape symbolic finite-state transducer with registers"""

    def __init__(
        self,
        states: list = None,
        registers: list = None,
        transitions: list = None,
        init_states: list = None,
        accepting_states: list = None,
        origin=None,
    ):
        assert states is None or all(isinstance(s, State) for s in states), states
        assert init_states is None or all(
            isinstance(s, State) for s in init_states
        ), init_states
        assert init_states is None or all(s in states for s in init_states), init_states
        assert accepting_states is None or all(
            isinstance(s, State) for s in accepting_states
        ), accepting_states
        assert accepting_states is None or all(
            s in states for s in accepting_states
        ), accepting_states
        assert registers is None or all(
            isinstance(r, Reg) for r in registers
        ), registers
        assert transitions is None or all(
            isinstance(t, Transition) for t in transitions
        ), transitions

        self._registers = registers
        # list of traces read by this transducer
        self._traces = set()

        super().__init__(states, transitions, init_states, accepting_states, origin)

    # FIXME: turn into a property
    def registers(self):
        return self._registers

    @property
    def traces(self):
        return self._traces

    def get_single_trace(self):
        """
        Get its only input trace or None if there is no single input trace
        """
        T = self.traces
        if len(T) == 1:
            return next(iter(T))
        return None

    def copy(self, new_origin=None):
        return SymbolicTransducer(
            states=self.states(),
            registers=[Reg(reg.value) for reg in self.registers() or ()],
            transitions=self.transitions(),
            init_states=self.initial_states(),
            accepting_states=self.accepting_states(),
            origin=new_origin or self.origin(),
        )

    def has_eps_transitions(self):
        return any((t.label.is_eps() for t in self.transitions()))

    def add_transition(self, t):
        for tr in t.label.symbols.keys():
            self._traces.add(tr)
        super().add_transition(t)

    def remove_redundant_states_once(self):
        states, trans, init, acc = self.get_usable_part()
        return SymbolicTransducer(
            states=list(states.values()),
            registers=[Reg(reg.value) for reg in self.registers() or ()],
            transitions=trans,
            init_states=init,
            accepting_states=acc,
            origin=self.origin(),
        )
