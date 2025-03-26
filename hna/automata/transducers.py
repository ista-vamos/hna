from hna.automata.transition_system import AccInitTransitionSystem, Transition, State


class Value:

    def __init__(self, v):
        self._v = v

    @property
    def value(self):
        return self._v

    def is_const(self) -> bool:
        return False

    def is_var(self) -> bool:
        return False

    def is_reg(self) -> bool:
        return False

    def is_eps(self) -> bool:
        return False


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


class Var(Value):
    def __init__(self, v):
        super().__init__(v)

    def is_var(self) -> bool:
        return True

    def __eq__(self, other):
        return isinstance(other, Var) and self.value == other.value

    def __hash__(self):
        return hash("v") ^ hash(self.value)

    def __str__(self):
        return str(self.value)


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


class Eps(Value):
    def __init__(self):
        super().__init__(None)

    def is_eps(self) -> bool:
        return True

    def __eq__(self, other):
        return isinstance(other, Eps)

    def __str__(self) -> str:
        return "ε"

    def __hash__(self):
        return hash("ε")


# ------------------------------------------------------------


class Condition:
    pass


class BinaryPredicate(Condition):
    def __init__(self, lhs, rhs):
        self._lhs = lhs
        self._rhs = rhs

    @property
    def lhs(self):
        return self._lhs

    @property
    def rhs(self):
        return self._rhs


class Eq(BinaryPredicate):
    def __init__(self, lhs, rhs):
        super().__init__(lhs, rhs)

    def __str__(self):
        return f"{self.lhs} = {self.rhs}"


class NEq(BinaryPredicate):
    def __init__(self, lhs, rhs):
        super().__init__(lhs, rhs)

    def __str__(self):
        return f"{self.lhs} ! {self.rhs}"


class Assignment:
    def __init__(self, to: Value, val: Value):
        self._to = to
        self._val = val

    @property
    def to(self):
        return self._to

    def val(self):
        return self._val

    def __str__(self):
        return f"{self.to} := {self.val}"


class TransitionLabel:
    def __init__(self, symbol: Value, condition: list, assign: list, output: Value):
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

    def __str__(self):
        return f"{self.symbol}{self.condition};{self.assignment}/{self.output}"


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


def merge_transducers(left, right):
    """
    Merge two transducers into a single transducer, renaming states of 'right' if the names conflict.
    That is, do a disjoint union.
    Also, clean initial and accepting states.
    """

    registers = left.registers()
    # registers = (
    #    right.registers() if not registers else (registers + (right.registers() or []))
    # )
    if right.registers():
        raise NotImplementedError("Rename conflicting registers")
    # we might need to rename states, keep the new names in this map
    renamed_states = {}
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

    return T
