from rvhyno.automata.transition_system import (
    AccInitTransitionSystem,
)


class Automaton(AccInitTransitionSystem):
    """
    Class representing a finite-state automaton

    :param states:
    """

    def __init__(
        self,
        states: list = None,
        transitions: list = None,
        init_states: list = None,
        acc_states: list = None,
        origin=None,
    ):
        super().__init__(states, transitions, init_states, acc_states, origin=origin)

    def is_deterministic(self) -> bool:
        """
        Return True if the automaton is deterministic, False otherwise
        """
        for tmap in self._transitions_from.values():
            for T in tmap.values():
                if len(T) > 1:
                    return False
        return True
