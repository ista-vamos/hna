from copy import copy


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
    """
    A variable representing a symbol of a trace.
    """

    def __init__(self, name):
        super().__init__(name)

    def is_var(self) -> bool:
        return True

    def __eq__(self, other):
        return isinstance(other, Var) and self.value == other.value

    def __hash__(self):
        return hash("v") ^ hash(self.value)

    def __repr__(self):
        return f"Var({self.value})"

    def __str__(self):
        return f"{self.value}"

    def c_code(self):
        return str(self)

    def ord(self):
        return "3", self.value, "z"


class Attr(Value):
    """Access an attribute of a variable, e.g., in(x)"""

    def __init__(self, var, attr):
        assert isinstance(var, (Var, Reg)), f"{var}: {type(var)}"
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
        return f"END({self.trace})"


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
        assert isinstance(to, Value), to
        assert isinstance(val, Value), val
        assert not to.is_eps(), to
        assert not val.is_eps(), val

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


# TODO: rename to "TransitionLabel" after renaming "SymbolicTransducer" to "MST" ("Multi-trace symbolic transducer")
class TransitionMultiLabel:
    """
    :param symbols: a dictionary mapping trace variables to symbols
                    (names that refer to the even read from the trace)
    """

    def __init__(self, symbols: dict, condition: list, assign: list, output: Value):
        assert all(isinstance(k, Var) for k in symbols.values()), symbols
        assert all(isinstance(k, TraceVariable) for k in symbols.keys()), symbols

        self._symbols = symbols
        self._cond = condition
        self._assign = assign
        self._output = output

    @property
    def symbols(self):
        return self._symbols

    @property
    def assignment(self):
        return self._assign

    @property
    def condition(self):
        return self._cond

    @property
    def output(self):
        return self._output

    @staticmethod
    def EPS():
        return TransitionMultiLabel({}, [], [], Eps())

    def is_eps(self):
        """
        Return `True` if the label is epsilon label in the classical sense: input-output epsilon with no conditions nor assignments.
        """
        return (
            self.is_output_eps()
            and self.is_input_eps()
            and (not self.condition)
            and (not self.assignment)
        )

    def is_input_eps(self):
        return not self.symbols

    def is_output_eps(self):
        return self.output.is_eps()

    def reset_trace(self, what, to):
        return TransitionMultiLabel(
            {(to if k == what else k): v for k, v in self.symbols.items()}, self.output
        )

    def __repr__(self):
        out = f" ↦ {self.output}" if self.output else ""
        assign = f";{', '.join(map(str, self.assignment))}" if self.assignment else ""
        cond = f"[{', '.join(map(str, self.condition))}]" if self.condition else ""
        return f"TransitionLabel({self.symbols or 'ε'}{cond}{assign}{out})"

    def __str__(self):
        out = f" ↦  {self.output}" if self.output else ""
        assign = f";{', '.join(map(str, self.assignment))}" if self.assignment else ""
        cond = f"[{', '.join(map(str, self.condition))}]" if self.condition else ""
        sym = ", ".join(f"{t}: {x}" for t, x in self.symbols.items())
        return f"({sym or 'ε'}){cond}{assign}{out}"
