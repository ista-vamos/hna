from hna.automata.transition_system import (
    Transition as TSTransition,
    AccInitTransitionSystem, State,
)

class Value:

    def __init__(self, v):
        self._v = v

    @property
    def value(self):
        return self._v

    def is_const(self) -> bool: return False
    def is_var(self) -> bool: return False
    def is_reg(self) -> bool: return False
    def is_eps(self) -> bool: return False

class Constant(Value):
    def __init__(self, v):
        super().__init__(v)
    def is_const(self) -> bool: return True

    def __eq__(self, other):
        return isinstance(other, Constant) and self.value == other.value


class Var(Value):
    def __init__(self, v):
        super().__init__(v)

    def is_var(self) -> bool: return True

    def __eq__(self, other):
        return isinstance(other, Var) and self.value == other.value


class Reg(Value):
    def __init__(self, v):
        super().__init__(v)

    def is_reg(self) -> bool: return True

    def __eq__(self, other):
        return isinstance(other, Reg) and self.value == other.value


class Eps(Value):
    def __init__(self):
        super().__init__(None)

    def is_eps(self) -> bool: return True

    def __eq__(self, other):
        return isinstance(other, Eps)

    def __str__(self) -> str:
        return "ε"

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
        return f'{self.lhs} = {self.rhs}'


class NEq(BinaryPredicate):
    def __init__(self, lhs, rhs):
        super().__init__(lhs, rhs)

    def __str__(self):
        return f'{self.lhs} ! {self.rhs}'

class Assignment:
    def __init__(self, to: Value, val: Value):
        self._to = to
        self._val = val

    @property
    def to(self): return self._to
    def val(self): return self._val

    def __str__(self):
        return f'{self.to} := {self.val}'

class Transition(TSTransition):
    def __init__(self, source: State, symbol: Value, condition: list, target: State, assign: list, output: Value, priority=0):
        super().__init__(source, symbol, target, priority)
        self._output = output
        self._assign = assign
        self._cond = condition

        # the transition does not change, precompute its str and hash,
        # because these are used a lot and we want them to be fast
        prio = f":{priority}" if priority != 0 else ""
        self._str = f"({source} --{symbol}{condition};{assign}/{output}{prio}-> {target})"
        self._hash = hash(str((source, target, symbol, condition, assign, output, priority)))

    @property
    def output(self):
        return self._output

    @property
    def symbol(self):
        return self.label

    @property
    def assignment(self):
        return self._assign

    @property
    def condition(self):
        return self._cond

    @staticmethod
    def get_eps(source: State, target: State):
        return Transition(source, Eps(), target)


    def dot_label(self):
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


def concat_transducers(left: SymbolicTransducer, right: SymbolicTransducer):
    T = SymbolicTransducer(states=left.states() + right.states(),
                           registers=left.registers() + right.registers(),
                           transitions=left.transitions()+right.transitions(),
                           init_states=left.initial_states(),
                           accepting_states=right.accepting_states()
                           )
    for acc, init in ((o, i) for o in left.accepting_states() for i in right.initial_states()):
        for init_out in right.transitions(init):
            new = init_out.copy()
            new.source = acc
            T.add_transition(new)
            if right.is_accepting(init):
                T.add_accepting(acc)

    return T

