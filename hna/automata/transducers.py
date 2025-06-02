from copy import copy
from itertools import chain

from hna.automata.transition_system import AccInitTransitionSystem, Transition, State


class Value:

    def __init__(self, v):
        self._v = v

    @property
    def value(self):
        return self._v

    @value.setter
    def value(self, v):
        self._v = v

    def is_const(self) -> bool:
        return False

    def is_var(self) -> bool:
        return False

    def is_attr(self) -> bool:
        return False

    def is_reg(self) -> bool:
        return False

    def is_eps(self) -> bool:
        return False

    def c_name(self):
        """A name usable in C code"""
        return f"{self.value}"

    def subst(self, s):
        what, by = s
        if self == what:
            return by
        return self

    def ord(self):
        """A tuple used for ordering this value"""
        return ("z", "z", "z")

    def __lt__(self, other):
        return self.ord() < other.ord()


class Constant(Value):
    def __init__(self, v):
        super().__init__(v)

    def is_const(self) -> bool:
        return True

    def __eq__(self, other):
        return isinstance(other, Constant) and self.value == other.value

    def __hash__(self):
        return hash("c") ^ hash(self.value)

    def __str__(self):
        return f"{self.value}𞁞"

    def __repr__(self):
        return f"{self.value}𞁞"

    def c_name(self):
        """A name usable in C code"""
        return f"'{self.value}'" if self.value.isalpha() else f"{self.value}"

    def ord(self):
        """A tuple used for ordering this value"""
        # NOTE: value can be int, because the comparison is short-circuiting
        # and if we compare to something else than a constant, the code
        # never gets to comparing the values and therefore there will be no invalid comparison
        return ("9", self.value, "z")


class Var(Value):
    def __init__(self, v):
        super().__init__(v)

    def is_var(self) -> bool:
        return True

    def __eq__(self, other):
        return isinstance(other, Var) and self.value == other.value

    def __hash__(self):
        return hash("v") ^ hash(self.value)

    def __repr__(self):
        return f"Var({self.value})"

    def __str__(self):
        return str(self.value)

    def ord(self):
        return "3", self.value, "z"


class Attr(Value):
    """Access an attribute of a variable, e.g., in(x)"""

    def __init__(self, var, attr):
        assert isinstance(var, (Var, Reg)), var
        super().__init__((var, attr))

    @property
    def var(self):
        return self.value[0]

    @property
    def attr(self):
        return self.value[1]

    def is_attr(self) -> bool:
        return True

    def __eq__(self, other):
        return isinstance(other, Attr) and self.value == other.value

    def __hash__(self):
        return hash("a") ^ hash(self.value)

    def __str__(self):
        v, a = self.value
        return f"{a}({v})"

    def __repr__(self):
        v, a = self.value
        return f"Attr({a}, {v})"

    def c_name(self, op="->"):
        """A name usable in C code"""
        v, a = self.value
        return f"{v.c_name()}{op}{a}"

    def subst(self, s):
        what, by = s
        if self == what:
            return by

        v, a = self.value
        return Attr(v.subst(s), a)

    def ord(self):
        v, a = self.value
        return "1", a, v


class Reg(Value):
    def __init__(self, v):
        super().__init__(v)

    def is_reg(self) -> bool:
        return True

    def __eq__(self, other):
        return isinstance(other, Reg) and self.value == other.value

    def __hash__(self):
        return hash("r") ^ hash(self.value)

    def __str__(self):
        return f"{self.value}ᵣ"

    def __repr__(self):
        return f"Reg({self.value})"

    def ord(self):
        return "7", self.value, "z"


class Eps(Value):
    def __init__(self):
        super().__init__(None)

    def is_eps(self) -> bool:
        return True

    def __eq__(self, other):
        return isinstance(other, Eps)

    def __str__(self) -> str:
        return "ε"

    def __repr__(self):
        return "Eps()"

    def __hash__(self):
        return hash("ε")

    def subst(self, s):
        return self

    def ord(self):
        return "e", "z", "z"


# ------------------------------------------------------------


class Condition:
    pass


class TraceFinished:
    def __init__(self, t):
        self._trace = t

    @property
    def trace(self):
        return self._trace

    def subst(self, s):
        what, by = s
        new = copy(self)

        if what == self.trace:
            new._trace = by

        return new

    def c_code(self):
        return f"{self.trace}->finished()"

    def __str__(self) -> str:
        return f'END({self.trace})'




class BinaryPredicate(Condition):
    def __init__(self, lhs, rhs):
        self._lhs = lhs
        self._rhs = rhs

    @property
    def lhs(self):
        return self._lhs

    @lhs.setter
    def lhs(self, val):
        self._lhs = val

    @property
    def rhs(self):
        return self._rhs

    @rhs.setter
    def rhs(self, val):
        self._rhs = val

    def subst(self, s):
        what, by = s
        # we must copy the type of object
        # XXX: unfortunately, this way we also copy lhs and rhs that we then override.
        # If that should be a problem at some point, we'll switch to a more clever solution.
        new = copy(self)
        new._lhs = self._lhs.subst(s)
        new._rhs = self._rhs.subst(s)
        return new


class Eq(BinaryPredicate):
    def __init__(self, lhs, rhs):
        super().__init__(lhs, rhs)

    def __str__(self):
        return f"{self.lhs} = {self.rhs}"

    def __repr__(self):
        return f"Eq({self.lhs}, {self.rhs})"

    def c_code(self):
        return f"{self.lhs.c_name()} == {self.rhs.c_name()}"


class NEq(BinaryPredicate):
    def __init__(self, lhs, rhs):
        super().__init__(lhs, rhs)

    def __str__(self):
        return f"{self.lhs} ≠ {self.rhs}"

    def __repr__(self):
        return f"NEq({self.lhs}, {self.rhs})"

    def c_code(self):
        return f"{self.lhs.c_name()} != {self.rhs.c_name()}"


class Assignment:
    def __init__(self, to: Value, val: Value):
        self._to = to
        self._val = val

    @property
    def to(self):
        return self._to

    @property
    def val(self):
        return self._val

    def __str__(self):
        return f"{self.to}:={self.val}"

    def __repr__(self):
        return f"Assign({self.to}, {self.val})"

    def subst(self, s):
        what, by = s
        # we must copy the type of object
        # XXX: unfortunately, this way we also copy lhs and rhs that we then override.
        # If that should be a problem at some point, we'll switch to a more clever solution.
        new = copy(self)
        new._to = self._to.subst(s)
        new._val = self._val.subst(s)
        return new


class TransitionLabel:
    def __init__(
        self, symbol: (Value, tuple), condition: list, assign: list, output: Value
    ):
        assert not isinstance(
            symbol, Reg
        ), f"We do not allow a register to be transition symbol: {symbol}"
        self._symbol = symbol
        self._cond = condition
        self._assign = assign
        self._output = output

    @property
    def output(self):
        return self._output

    @property
    def symbol(self):
        return self._symbol

    @property
    def assignment(self):
        return self._assign

    @property
    def condition(self):
        return self._cond

    @staticmethod
    def EPS():
        return TransitionLabel(Eps(), [], [], Eps())

    def is_eps(self):
        return (
            self.symbol.is_eps()
            and self.output.is_eps()
            and not self.condition
            and not self.assignment
        )

    def is_input_eps(self):
        return self.symbol.is_eps()

    def is_output_eps(self):
        return self.output.is_eps()

    def __repr__(self):
        out = f" / {self.output}" if self.output else ""
        assign = f";{', '.join(map(str, self.assignment))}" if self.assignment else ""
        cond = f"[{', '.join(map(str, self.condition))}]" if self.condition else ""
        return f"TransitionLabel({self.symbol}{cond}{assign}{out})"

    def __str__(self):
        out = f" / {self.output}" if self.output else ""
        assign = f";{', '.join(map(str, self.assignment))}" if self.assignment else ""
        cond = f"[{', '.join(map(str, self.condition))}]" if self.condition else ""
        return f"{self.symbol}{cond}{assign}{out}"


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

    def registers(self):
        return self._registers

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


def concat_transducers(left: SymbolicTransducer, right: SymbolicTransducer):
    T, renamed_states = merge_transducers(left, right)
    # set new initial and accepting states
    for s in left.initial_states():
        T.add_init(s)
    for s in right.accepting_states():
        T.add_accepting(renamed_states.get(s, s))

    for l_acc, r_init in (
        (a, i) for a in left.accepting_states() for i in right.initial_states()
    ):
        T_r_init = renamed_states.get(r_init, r_init)
        for out in (t for vals in T.transitions(T_r_init).values() for t in vals):
            T.add_transition(Transition(l_acc, out.label, out.target))
            if right.is_accepting(r_init):
                T.add_accepting(l_acc)

    return T


def union_transducers(
    left: SymbolicTransducer, right: SymbolicTransducer
) -> SymbolicTransducer:
    T, renamed_states = merge_transducers(left, right)
    # set new accepting states
    for s in left.accepting_states():
        T.add_accepting(s)
    for s in right.accepting_states():
        T.add_accepting(renamed_states.get(s, s))

    new_init = add_new_init(T)

    for old_init in left.initial_states():
        for out in T.transitions_from(old_init):
            T.add_transition(Transition(new_init, out.label, out.target))
            if left.is_accepting(old_init):
                T.add_accepting(new_init)
    for old_init in right.initial_states():
        old_init_r = renamed_states.get(old_init, old_init)
        for out in T.transitions_from(old_init_r):
            T.add_transition(Transition(new_init, out.label, out.target))
            if right.is_accepting(old_init):
                T.add_accepting(new_init)

    return T


def add_new_init(T):
    # find an unused new init name
    new_init_name = "0"
    while T.get(new_init_name) is not None:
        new_init_name += "0"
    new_init = State(new_init_name)
    T.add_state(new_init)
    T.add_init(new_init)
    return new_init


def merge_transducers(left, right):
    """
    Merge two transducers into a single transducer, renaming states of 'right' if the names conflict.
    That is, do a disjoint union.
    Also, clean initial and accepting states.
    """

    if left.registers() and right.registers():
        raise NotImplementedError("Rename conflicting registers")

    registers = ((left.registers() or []) + (right.registers() or [])) or None
    # we might need to rename states, keep the new names in this map
    renamed_states = {}
    renamed_registers = {}
    states = left.states().copy()
    # FIXME: this might be inefficient
    for r_state in right.states():
        if r_state in states:
            new_state = State(f"{r_state.name()}'")
            renamed_states[r_state] = new_state
            r_state = new_state
        states.append(r_state)
    transitions = left.transitions().copy()
    if not renamed_states:
        transitions += right.transitions()
    else:
        for rt in right.transitions():
            source, target = rt.source, rt.target
            transitions.append(
                Transition(
                    renamed_states.get(source, source),
                    rt.label,
                    renamed_states.get(target, target),
                )
            )
    T = SymbolicTransducer(
        states=states,
        registers=registers,
        transitions=transitions,
    )
    return T, renamed_states


def remove_epsilon_steps(eT: SymbolicTransducer) -> SymbolicTransducer:
    """Return the transducer `eT` without epsilon steps"""
    T = SymbolicTransducer(
        states=eT.states(),
        registers=eT.registers(),
        transitions=[],
        init_states=eT.initial_states(),
        accepting_states=eT.accepting_states(),
        origin=eT.origin(),
    )

    for trans in eT.transitions():
        if not trans.is_eps():
            T.add_transition(trans)
            continue

        for target_out in eT.transitions(trans.target):
            new = target_out.copy()
            new.source = trans.source
            T.add_transition(new)
            if eT.is_accepting(trans.target):
                T.add_accepting(trans.source)

    return T


def iterate_transducer(T1: SymbolicTransducer) -> SymbolicTransducer:
    assert T1 is not None
    T = T1.copy(new_origin=T1)
    for acc, init in (
        (o, i) for o in T1.accepting_states() for i in T1.initial_states()
    ):
        for init_out in (
            t for vals in T1.transitions(init, default=()).values() for t in vals
        ):
            assert isinstance(init_out, Transition), (init_out, type(init_out))
            T.add_transition(Transition(acc, init_out.label, init_out.target))
            if T1.is_accepting(init):
                T.add_accepting(acc)

    # also, we must make sure we accept the empty word
    # check if the initial states are accepting
    if not all(T.is_accepting(s) for s in T.initial_states()):
        # check if we can just mark the states accepting -- that we can do if they have no
        # incoming edges
        if all(not T.transitions_to(s) for s in T.initial_states()):
            for s in T.initial_states():
                T.add_accepting(s)
        else:
            # we must add a new initial state that accepts epsilon and then continues to T
            # (basically the union with a transducer that accepts epsilon)
            new_init = add_new_init(T)
            T.add_accepting(new_init)
            for old_init in T1.initial_states():
                for out in T.transitions_from(old_init):
                    T.add_transition(Transition(new_init, out.label, out.target))

    return T


def compose_transducers(
    inner: SymbolicTransducer, outer: SymbolicTransducer, origin=None
) -> SymbolicTransducer:
    """
    Compute the sequential composition outer(inner).
    """

    assert (
        not inner.has_eps_transitions()
    ), "Transducers in the composition cannot have epsilon transitions"
    assert (
        not outer.has_eps_transitions()
    ), "Transducers in the composition cannot have epsilon transitions"

    # pairs of states that we will later translate to State. But for now, it is more comfortable
    # to work with pairs of states.
    states = set()
    # triple (source, label, target) where source and target are pairs of states.
    # We will later translate them into Transition classes
    transitions = []
    queue = [(ii, oi) for ii in inner.initial_states() for oi in outer.initial_states()]
    new_queue = []

    while queue:
        for state_pair in queue:
            # print(f"CUR: {state_pair[0]},{state_pair[1]}")
            if state_pair in states:
                continue
            states.add(state_pair)

            for outer_t in outer.transitions_from(state_pair[1]):
                # handle epsilon steps of outer transducer
                if outer_t.label.is_input_eps():
                    new_target = (state_pair[0], outer_t.target)
                    transitions.append(state_pair, outer_t.label, new_target)
                    new_queue.append(new_target)

            for inner_t, outer_t in (
                (it, ot)
                for it in inner.transitions_from(state_pair[0])
                for ot in outer.transitions_from(state_pair[1])
            ):
                if outer_t.label.is_input_eps():
                    # these were handled separately
                    continue

                # combine the transitions
                new_t = compose_transitions(inner_t, outer_t)
                if new_t is None:
                    # the transition had UNSAT condition
                    continue
                assert new_t[0] == state_pair
                assert new_t[0] == (inner_t.source, outer_t.source)
                assert new_t[2] == (inner_t.target, outer_t.target)
                # print(
                #    f"NEW_T: {new_t[0][0]},{new_t[0][1]} - {new_t[1]} -> {new_t[2][0]},{new_t[2][1]}"
                # )
                transitions.append(new_t)
                # new_t[2] is the target of the new to-be-transition
                if new_t[2] not in states:
                    new_queue.append(new_t[2])

        queue, new_queue = new_queue, []

    states = {(i, o): State(f"({i},{o})") for (i, o) in states}

    registers = inner.registers()
    registers = (
        outer.registers() if not registers else (registers + (outer.registers() or []))
    )
    return SymbolicTransducer(
        states=list(states.values()),
        registers=registers,
        transitions=[Transition(states[t[0]], t[1], states[t[2]]) for t in transitions],
        init_states=[
            states[s]
            for s in states.keys()
            if inner.is_initial(s[0]) and outer.is_initial(s[1])
        ],
        accepting_states=[
            states[s]
            for s in states.keys()
            if inner.is_accepting(s[0]) and outer.is_accepting(s[1])
        ],
        origin=origin,
    )


def compose_transitions(inner: Transition, outer: Transition) -> Transition:
    inner_l: TransitionLabel = inner.label
    outer_l: TransitionLabel = outer.label

    subst = (outer_l.symbol, inner_l.output)
    condition = simplify_condition(
        inner_l.condition + substitute_lst(outer_l.condition, subst)
    )
    if condition is None:  # UNSAT condition
        return None

    label = TransitionLabel(
        symbol=inner_l.symbol,
        condition=condition,
        assign=(
            (inner_l.assignment or []) + substitute_lst(outer_l.assignment or [], subst)
        )
        or None,
        output=outer_l.output.subst(subst),
    )

    return (inner.source, outer.source), label, (inner.target, outer.target)


def normalize_term(term):
    """
    Any variable is 'smaller' than any register, and any register is smaller than any constant.
    Variables, registers, and constants are ordered lexicographically.
    This function outputs the smaller of (term.lhs, term.rhs) or (term.rhs, term.lhs).
    NOTE: it modifies the original term!
    """
    if not term.lhs < term.rhs:
        term.rhs, term.lhs = term.lhs, term.rhs
    return term


def remove_duplicates(cond):
    return list(set(normalize_term(c) for c in cond))


def remove_trivial(cond):
    return [c for c in cond if not isinstance(c, Eq) or c.lhs != c.rhs]


def get_eq_constants(eq_classes):
    consts = {}
    for eqcl in eq_classes.values():
        constants = [elem for elem in eqcl if isinstance(elem, Constant)]
        if len(constants) > 1:
            return None  # two different constants should equal
        elif not constants:
            continue

        for elem in eqcl:
            if isinstance(elem, Constant):
                continue
            assert (elem not in consts) or consts[elem] == constants[0], (
                eq_classes,
                constants,
                consts,
            )
            consts[elem] = constants[0]

    return consts


def propagate_constants(cond, consts):
    for s in consts.items():
        cond = substitute_lst(cond, s)
    cond += [Eq(x, c) for x, c in consts.items()]
    return remove_trivial(remove_duplicates(cond))


def simplify_condition(cond):
    # remove repeated terms
    cond = remove_duplicates(cond)
    cond = remove_trivial(cond)

    # TODO: do this properly with SMT solver?
    eq_classes = get_eq_classes(cond)

    consts = get_eq_constants(eq_classes)
    if consts is None:
        # UNSAT condition, two different constants should equal
        return None

    for c in (c for c in cond if isinstance(c, NEq)):
        if c.rhs in eq_classes.get(c.lhs, ()):
            # UNSAT condition, there's a claim that two elements
            # should be the same and different at the same time
            return None

    cond = propagate_constants(cond, consts)
    # TODO: simplify the condition by constant propagation

    return cond


def get_eq_classes(cond):
    eq_classes = {}
    for c in (x for x in cond if isinstance(x, Eq)):
        # FIXME: this is not very efficient, but we'll not likely have problem with this
        C1 = eq_classes.setdefault(c.lhs, set((c.lhs,)))
        C2 = eq_classes.setdefault(c.rhs, set((c.rhs,)))
        assert c.lhs in C1
        assert c.rhs in C2
        C = C1.union(C2)
        for x in C:
            eq_classes[x] = C
    return eq_classes


def substitute_lst(lst, subst):
    return [x.subst(subst) for x in lst]


def parse_condition(cond, var, attrs):
    if not cond:
        return []

    terms = cond.split(",")
    cond = []
    for term in terms:
        lhs, op, rhs = term.split()
        lhs = Attr(var, lhs) if lhs in attrs else Constant(lhs)
        rhs = Attr(var, rhs) if rhs in attrs else Constant(rhs)
        if op in ("==", "="):
            Ctor = Eq
        elif op == "!=":
            Ctor = NEq
        cond.append(Ctor(lhs, rhs))
    return cond


def transducer_from_yaml(path, attrs):
    from yaml import safe_load
    from hna.hna.parser.parser import parse_edge

    attrs = set(x[0] for x in attrs)
    T = SymbolicTransducer(origin=path)

    with open(path, "r") as stream:
        data = safe_load(stream)
        for nd in data["transducer"]["nodes"]:
            T.add_state(State(str(nd)))
        for edge in data["transducer"]["edges"]:
            if edge.get("assignment"):
                raise NotImplementedError(
                    "The code does not support assignments in user functions yet"
                )

            source, target = parse_edge(edge["edge"])
            symbol = edge["symbol"]
            var = Var(symbol)
            output = edge["output"]
            if output == symbol:
                output = var
            elif output == r"\eps":
                output = Eps()
            else:
                Constant(output)

            T.add_transition(
                Transition(
                    T.get(str(source)),
                    TransitionLabel(
                        var,
                        parse_condition(edge.get("condition"), var, attrs),
                        None,
                        output,
                    ),
                    T.get(str(target)),
                )
            )

        T.add_init(T.get(str(data["transducer"]["init"])))
        for nd in data["transducer"]["accept"]:
            T.add_accepting(T.get(str(nd)))

        return str(data["transducer"]["name"]), T
