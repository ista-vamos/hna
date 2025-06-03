from sys import stdout


class State:
    """
    State of an automaton
    """

    def __init__(self, name):
        # assert isinstance(name, str), (name, type(name))
        self._name = name

    def name(self):
        return self._name

    def __eq__(self, other: "State") -> bool:
        assert isinstance(other, State), other
        return self._name == other._name

    def __hash__(self):
        return self._name.__hash__()

    def __repr__(self):
        return f"State({self._name})"

    def __str__(self):
        return str(self._name)

    def dot_name(self):
        return str(self._name)


class Transition:
    """Transition of an automaton"""

    def __init__(self, source, label, target, priority=0):
        assert isinstance(source, State), source
        assert isinstance(target, State), target
        self._source = source
        self._target = target
        self._label = label
        self._priority = priority
        # the transition does not change, precompute its str and hash,
        # because these are used a lot and we want them to be fast
        prio = f":{priority}" if self._priority != 0 else ""
        self._str = f"({source} --|{label}{prio}|-> {target})"
        self._hash = hash((source, target, label, priority))

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
        return self._str == other._str

    # return (
    #    self._source == other._source
    #    and self._label == other._label
    #    and self._target == other._target
    #    and self._priority == other._priority
    # )

    def __str__(self):
        return self._str

    def __hash__(self):
        return self._hash

    def dot_label(self):
        return str(self._label)


class TransitionSystem:
    """Class representing a finite-state automaton"""

    _id_cnt = 0

    def __init__(
        self,
        states: list = None,
        transitions: list = None,
        labeling: dict = None,
        origin=None,
    ):
        TransitionSystem._id_cnt += 1
        self._id = TransitionSystem._id_cnt
        self._states = {}
        self._transitions = []
        self._labeling = labeling or {}
        self._transitions_from = {}
        self._transitions_to = {}
        # we number the states from 0
        self._state_to_id = {}
        self._last_id = 0
        # the object this automaton was created for
        # a formula or another automata, etc.
        # NOTE: optional field, may not be set
        self._origin = origin

        # use `add_state` and `add_transition` so that the states are assigned the ID
        # and states and transitions are copied
        for s in states or ():
            self.add_state(s)
        for t in transitions or ():
            self.add_transition(t)

    def __getitem__(self, item):
        return self._states[item]

    def get_id(self):
        return self._id

    def __eq__(self, other):
        raise RuntimeError(
            f"Class {self} have no __eq__, you can try use get_id() where suitable"
        )

    def get(self, label_or_state) -> State:
        """
        Get the state by its label, or, if State is given instead of label,
        get our copy of the state (the state from this TS with the same label)
        """
        if isinstance(label_or_state, State):
            label_or_state = label_or_state.name()
        return self._states.get(label_or_state)

    def get_state_id(self, item: State) -> int:
        return self._state_to_id[item]

    def has_label(self, state, label):
        """Check if a given state has assigned a given label (label is not the same as the name of the state)"""
        states_with_label = self.states_with_label(label)
        if states_with_label is None:
            return False
        return state in states_with_label

    def states_with_label(self, label):
        return self._labeling.get(label)

    def add_state(self, state):
        assert isinstance(state, State), (state, type(state))
        assert (
            state not in self._states.values()
        ), f"{state} should NOT be in [{', '.join(map(str, self._states.values()))}]"

        self._states[state.name()] = state
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
        self._transitions_from.setdefault(t.source, {}).setdefault(t.label, []).append(
            t
        )
        self._transitions_to.setdefault(t.target, {}).setdefault(t.label, []).append(t)

    def transitions(self, state: State = None, a=None, default=None):
        """
        Return transitions from the automaton.

        If no optional arguments are provided, return the whole map `symbol: List[Transition]`
        (the automaton might be non-deterministic).
        If `state` is provided, return transitions that leave the given state.
        If also `a` is provided, return the list of transitions that leave the given state under the letter `a`.

        `default` parameter states what to return if no transitions that match the arguments are found.
        """
        if state is None:
            return self._transitions
        M = self._transitions_from.get(state)
        if M is None:
            return default
        if a is None:
            return M
        return M.get(a) or default

    def transitions_to(self, state: State):
        T = self._transitions_to.get(state)
        if T is None:
            return []
        return [t for vals in T.values() for t in vals]

    def transitions_from(self, state: State):
        T = self._transitions_from.get(state)
        if T is None:
            return []
        return [t for vals in T.values() for t in vals]

    def clear_transitions(self):
        t, tm = self._transitions, self._transitions_from
        self._transitions, self._transitions_from = [], {}
        return t, tm

    def states(self):
        return list(self._states.values())

    def origin(self):
        return self._origin


class AccInitTransitionSystem(TransitionSystem):
    def __init__(
        self,
        states: list = None,
        transitions: list = None,
        init_states: list = None,
        acc_states: list = None,
        origin=None,
    ):
        super().__init__(
            states,
            transitions,
            labeling={"accepting": acc_states or [], "initial": init_states or []},
            origin=origin,
        )

    def initial_states(self):
        return self.states_with_label("initial")

    def add_init(self, state):
        assert isinstance(state, State), (state, type(state))
        assert state in self._states.values()
        if state not in self.initial_states():
            self.initial_states().append(state)

    def is_initial(self, state):
        assert isinstance(state, State), (state, type(state))
        return self.has_label(state, "initial")

    def accepting_states(self):
        return self.states_with_label("accepting")

    def add_accepting(self, state):
        assert isinstance(state, State), (state, type(state))
        assert state in self._states.values()
        if state not in self.accepting_states():
            self.accepting_states().append(state)

    def is_accepting(self, state):
        assert isinstance(state, State), (state, type(state))
        return self.has_label(state, "accepting")

    def remove_redundant_states_once(self):
        """Remove unreachable states and states from which no accepting state is reachable"""
        # raise NotImplementedError("Not working yet")
        # get reachable states
        queue = self.initial_states().copy()
        accessible = set()
        new_queue = []
        while queue:
            for state in queue:
                if state not in accessible:
                    accessible.add(state)
                    new_queue.extend(t.target for t in self.transitions_from(state))
            queue, new_queue = new_queue, []

        # now, from reachable accepting states look backward for coaccessible states
        coaccessible = set()
        queue = [s for s in self.accepting_states() if s in accessible]
        assert new_queue == []
        while queue:
            for state in queue:
                if state not in coaccessible:
                    coaccessible.add(state)
                    new_queue.extend(t.source for t in self.transitions_to(state) or ())
            queue, new_queue = new_queue, []

        # the variables should be re-named, but...
        accessible.intersection_update(coaccessible)

        changed = len(accessible) < len(self._states)
        self._states = {s.name(): s for s in self.states() if s in accessible}
        self._transitions = [
            t
            for t in self.transitions()
            if t.source in accessible and t.target in accessible
        ]
        self._labeling["initial"] = [
            s for s in self.initial_states() if s in accessible
        ]
        self._labeling["accepting"] = [
            s for s in self.accepting_states() if s in accessible
        ]

        # FIXME
        # Update also mappings, etc.
        print(
            "FIXME: update mappings, otherwise the transducers cannot be used after this method"
        )

    def to_dot(self, output=stdout):
        print("digraph {", file=output)
        for _, state in self._states.items():
            attrs = ", color=darkgreen" if self.is_accepting(state) else ""
            attrs += ", shape=box" if self.is_initial(state) else ""
            print(
                f'  "N{self.get_state_id(state)}"[label="<{self.get_state_id(state)}> {state.dot_name()}" {attrs}]',
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
        self.dump_stats(output)

    # dump stats
    def dump_stats(self, output=stdout):
        print("\n/* -- statistics -- */", file=output)
        print(f"//  # states: {len(self._states)}", file=output)
        print(f"//  # transitions: {len(self._transitions)}", file=output)
        print(f"//  # init. states: {len(self.initial_states())}", file=output)
        print(f"//  # acc. states: {len(self.accepting_states())}", file=output)

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
                f"  {{ data: {{ id:  '{transition.name}{prio}', source: '{transition.source.name()}', target: '{transition.target.name()}' }} }},",
                file=output,
            )
        print("  ]", file=output)
        print("}", file=output)
