from sys import stdout


class State:
    """
    State of an automaton
    """

    def __init__(self, label):
        self._label = label

    def label(self):
        return self._label

    def __eq__(self, other: "State") -> bool:
        assert isinstance(other, State), other
        return self._label == other._label

    def __hash__(self):
        return self._label.__hash__()

    def __str__(self):
        return f"State({self._label})"

    def dot_label(self):
        return str(self._label)


class Transition:
    """
    Transition of an automaton
    """

    def __init__(self, source, label, target, priority=0):
        self._source = source
        self._target = target
        self._label = label
        self._priority = priority

    @property
    def source(self):
        return self._source

    @property
    def target(self):
        return self._target

    @property
    def label(self):
        return self._label

    @property
    def priority(self):
        return self._priority

    def __eq__(self, other):
        return (
            self._source == other._source
            and self._label == other._label
            and self._target == other._target
            and self._priority == other._priority
        )

    def __str__(self):
        prio = f":{self._priority}" if self._priority != 0 else ""
        return f"({self._source} -[{self._label}{prio}]-> {self._target})"

    def __hash__(self):
        return hash((self._source, self._target, self._label, self._priority))

    def dot_label(self):
        return str(self._label)


class Automaton:
    """
    Class representing an automaton
    """

    def __init__(
        self,
        states: list = None,
        transitions: list = None,
        init_states: list = None,
        acc_states: list = None,
        origin=None,
    ):
        self._states = {}
        # use `add_state` so that the states are assigned the ID
        for s in states or ():
            self.add_state(s)
        self._transitions = transitions or []
        self._initial_states = init_states or []
        self._accepting_states = acc_states or []
        self._transitions_mapping = {}
        # we number the states from 0
        self._state_to_id = {}
        self._last_id = 0
        # the object this automaton was created for
        # a formula or another automata, etc.
        # NOTE: optional field, may not be set
        self._origin = origin

    def __getitem__(self, item):
        return self._states[item]

    def get(self, item) -> State:
        """
        Get the state by its label
        """
        return self._states.get(item)

    def get_state_id(self, item: State) -> int:
        return self._state_to_id[item]

    def initial_states(self):
        return self._initial_states

    def accepting_states(self):
        return self._accepting_states

    def add_state(self, state):
        assert isinstance(state, State), (state, type(state))
        assert (
            state not in self._states.values()
        ), f"{state} is in [{', '.join(map(str, self._states.values()))}]"

        self._states[state.label()] = state
        self._state_to_id[state] = self._last_id
        self._last_id += 1

    def get_or_create_state(self, label):
        state = self._states.get(label)
        if state is None:
            state = State(label)
            self.add_state(state)
        return state

    def add_transition(self, t):
        assert isinstance(t, Transition), (t, type(t))
        assert (
            t not in self._transitions
        ), f"{t} in {', '.join(map(str, self._transitions))}"
        self._transitions.append(t)
        self._transitions_mapping.setdefault(t.source, {}).setdefault(
            t.label, []
        ).append(t)

    def transitions(self, state: State = None, a=None, default=None):
        if state is None:
            return self._transitions
        M = self._transitions_mapping.get(state)
        if M is None:
            return default
        if a is None:
            return M
        return M.get(a) or default

    def states(self):
        return list(self._states.values())

    def add_init(self, state):
        assert isinstance(state, State), (state, type(state))
        assert state in self._states.values()
        self._initial_states.append(state)

    def add_accepting(self, state):
        assert isinstance(state, State), (state, type(state))
        assert state in self._states.values()
        self._accepting_states.append(state)

    def is_accepting(self, state):
        assert isinstance(state, State), (state, type(state))
        return state in self._accepting_states

    def is_initial(self, state):
        assert isinstance(state, State), (state, type(state))
        return state in self._initial_states

    def origin(self):
        return self._origin

    def is_deterministic(self) -> bool:
        """
        Return True if the automaton is deterministic, False otherwise
        """
        for tmap in self._transitions_mapping.values():
            for T in tmap.values():
                if len(T) > 1:
                    return False
        return True

    def to_dot(self, output=stdout):
        print("digraph {", file=output)
        for _, state in self._states.items():
            attrs = ", color=darkgreen" if self.is_accepting(state) else ""
            attrs += ", shape=box" if self.is_initial(state) else ""
            print(
                f'  "N{self.get_state_id(state)}"[label="<{self.get_state_id(state)}> {state.dot_label()}" {attrs}]',
                file=output,
            )
        print("", file=output)
        for transition in self._transitions:
            prio = transition.priority
            prio = f"|{prio}" if prio != 0 else ""
            print(
                f'  "N{self.get_state_id(transition.source)}" -> "N{self.get_state_id(transition.target)}"[label="{transition.dot_label()}{prio}"]',
                file=output,
            )
        print("}", file=output)

        # dump stats
        print("\n/* -- statistics -- */", file=output)
        print(f"//  # states: {len(self._states)}", file=output)
        print(f"//  # transitions: {len(self._transitions)}", file=output)
        print(f"//  # init. states: {len(self._initial_states)}", file=output)
        print(f"//  # acc. states: {len(self._accepting_states)}", file=output)

    def to_json(self, output=stdout):
        print("{", file=output)
        print("  nodes: [", file=output)
        for label, state in self._states.items():
            print(
                f"  {{ data: {{ id: '{label}', init: '{self.is_initial(state)}', accepting: '{self.is_accepting(state)}'  }} }},",
                file=output,
            )
        print("  ],", file=output)
        print("", file=output)
        print("  edges: [", file=output)
        for transition in self._transitions:
            prio = transition.priority
            prio = f"|{prio}" if prio != 0 else ""
            print(
                f"  {{ data: {{ id:  '{transition.label}{prio}', source: '{transition.source.label()}', target: '{transition.target.label()}' }} }},",
                file=output,
            )
        print("  ]", file=output)
        print("}", file=output)
