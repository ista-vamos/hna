from sys import stdout


class State:
    def __init__(self, label):
        self._label = label

    def label(self):
        return self._label

    def __eq__(self, other):
        return self._label == other._label

    def __hash__(self):
        return self._label.__hash__()

    def __str__(self):
        return f"State({self._label})"


class Transition:
    def __init__(self, source, label, target):
        self._source = source
        self._target = target
        self._label = label

    @property
    def source(self):
        return self._source

    @property
    def target(self):
        return self._target

    @property
    def label(self):
        return self._label

    def __eq__(self, other):
        return (
            self._source == other._source
            and self._label == other._label
            and self._target == other._target
        )

    def __str__(self):
        return f"({self._source} -[{self._label}]-> {self._target})"


class Automaton:
    def __init__(
        self,
        states: list = None,
        transitions: list = None,
        init_states: list = None,
        acc_states: list = None,
    ):
        self._states = states or {}
        self._transitions = transitions or []
        self._initial_states = init_states or []
        self._accepting_states = acc_states or []

    def __getitem__(self, item):
        return self._states[item]

    def get(self, item):
        return self._states.get(item)

    def add_state(self, state):
        assert isinstance(state, State), (state, type(state))
        assert (
            state not in self._states
        ), f"{state} is in [{', '.join(map(str, self._states.values()))}]"
        self._states[state.label()] = state

    def add_transition(self, t):
        assert isinstance(t, Transition), (t, type(t))
        assert t not in self._transitions, (t, self._transitions)
        self._transitions.append(t)

    def to_dot(self, output=stdout):
        print("digraph {", file=output)
        for state in self._states.keys():
            print(f'  "{state}"[label="{state}"]', file=output)
        print("", file=output)
        for transition in self._transitions:
            print(
                f'  "{transition.source.label()}" -> "{transition.target.label()}"[label="{transition.label}"]',
                file=output,
            )
        print("}", file=output)
