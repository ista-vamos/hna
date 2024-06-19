from copy import copy
from typing import Any, Callable, List, Optional, Set, Union

from lark.lexer import Token

"""
formula.py defines a formula of HNL logic and
basic methods for their manipulation.

NOTE: The methods are not very optimized and we could definitely improve on that,
but so far they haven't been a bottle-neck.
"""


def cached_str(m):
    def new_str(self):
        if not self._cached_str:
            self._cached_str = m(self)
        return self._cached_str

    return new_str


class DerivativesSet(set):
    def __init__(self, *args) -> None:
        super().__init__((x.simplify() for x in args))
        self._cached_str = None

    def __add__(self, other: "DerivativesSet") -> "DerivativesSet":
        return DerivativesSet(*self, *other)

    def derivative(self, wrt):
        return DerivativesSet((x.derivative(wrt) for x in self))

    def is_empty(self) -> bool:
        return len(self) == 0

    @cached_str
    def __str__(self) -> str:
        return f"{{{','.join(map(str, self))}}}"


class Formula:
    """
    Formula of Hypernode Logic (HNL)
    """

    def __init__(self, children: Optional[List["Formula"]] = None) -> None:
        self.children = children or []
        all(map(lambda x: isinstance(x, Formula), self.children)), children
        # the __str__() often calls __str__() of subformulas recursively, which is expensive.
        # Since it should always return the same, just cache the result here
        self._cached_str = None

    def __hash__(self) -> int:
        return str(self).__hash__()

    def __eq__(self, other: "Formula") -> bool:
        return str(self) == str(other)

    def quantifiers(self) -> List["Quantifier"]:
        """
        Return all quantifiers from the formula
        """
        return [t for c in self.children for t in c.quantifiers()]

    def trace_variables(self) -> List["TraceVariable"]:
        """
        Get all trace variables from this formula
        """
        return list(set((t for c in self.children for t in c.trace_variables())))

    def program_variable_occurrences(self) -> List["ProgramVariable"]:
        """
        Get all occurrences of program variables from this formula
        """
        return [t for c in self.children for t in c.program_variable_occurrences()]

    def program_variables(self) -> List["ProgramVariable"]:
        """
        Get all trace variables from this formula
        """
        return list(set((t for c in self.children for t in c.program_variables())))

    def functions(self) -> List["Function"]:
        """
        Get all functions from this formula
        """
        return list(set((t for c in self.children for t in c.functions())))

    def constants(self) -> List["Constant"]:
        """
        Get all constants used in this formula
        """
        return list(set((t for c in self.children for t in c.constants())))

    def problems(self) -> List[str]:
        """
        Perform some checks if the formula is well-defined
        and return a list of problems that were found if any.
        """
        return []

    def visit_bottom_up(self, fn: Callable) -> None:
        """
        Visit recursively all children bottom up
        and call `fn(self)` for each visited formula.
        """
        for child in self.children:
            child.visit(fn)
        fn(self)

    def visit_top_down(self, fn: Callable) -> None:
        """
        Visit recursively all children top down
        and call `fn(self)` for each visited formula.
        """
        fn(self)
        for child in self.children:
            child.visit(fn)

    visit = visit_bottom_up

    def is_simple(self) -> bool:
        """
        Return True if the formula is simple, i.e., it does not contain
        multiple program variables on either side of prefixing relation
        TODO: and is not inside iteration
        """
        return all((c.is_simple() for c in self.children))

    def simplify(self) -> "Formula":
        """
        Simplify the formula. This is not in-situ operation, it returns possibly a new object
        """
        return self

    def copy(self):
        """
        Create a copy of this formula that can be modified.

        IMPORTANT: do not print the formula before the modifications are done,
        or clean the str cache after that.
        """
        s = copy(self)
        s._cached_str = None
        return s

    def remove_stutter_reductions(self) -> "Formula":
        """
        Create a formula from this one that is the same expect that every
        sub-formula of the form `StutterReduction(F)` is replaced by `F`
        """
        # XXX: we use only a shallow copy because the sub-formulas
        # should not be modified in-place anywhere.
        # If this assumption is violated, we must use a deep copy
        new_self = self.copy()

        children = []
        for c in self.children:
            x = c
            while isinstance(x, StutterReduce):
                x = x.children[0]
            nc = x.remove_stutter_reductions()
            children.append(nc)
        new_self.children = children

        return new_self

    def substitute(self, S):
        if self in S:
            return S[self].copy()

        new_self = self.copy()
        new_self.children = [c.substitute(S) for c in self.children]

        # Special cases
        ### XXX: these should be children too (or inherit the substitute method
        # instead of these if blocks)
        if isinstance(self, ProgramVariable):
            new_self.trace = self.trace.substitute(S)
        elif isinstance(self, Quantifier):
            new_self.var = self.var.substitute(S)
        elif isinstance(self, Function):
            new_self.traces = [t.substitute(S) for t in self.traces]

        return new_self


class FormulaWithLookahead(Formula):
    def __init__(self, formula: Formula, lookahead: Formula) -> None:
        super().__init__([formula])
        self.formula: Formula = formula
        self.lookahead: Formula = lookahead

    def simplify(self) -> Formula:
        x = self.formula.simplify()
        if x == EPSILON:
            return x
        return FormulaWithLookahead(x, self.lookahead.simplify())

    def remove_stutter_reductions(self) -> Formula:
        return FormulaWithLookahead(
            self.formula.remove_stutter_reductions(), self.lookahead
        )

    def _lookahead_matches_letter(self, a):
        lh = self.lookahead
        if isinstance(lh, Not):
            assert isinstance(lh.children[0], Constant), lh
            if lh.children[0].equiv(a):
                return False
        else:
            assert isinstance(lh, Constant), lh
            if not lh.equiv(a):
                return False

        return True

    def derivative(self, wrt) -> Formula:
        # check the match of the lookahead
        if not self._lookahead_matches_letter(wrt):
            return DerivativesSet()

        return self.formula.derivative(wrt)

    def non_empty(self):
        for a in self.formula.first():
            if isinstance(a, ProgramVariable) or self._lookahead_matches_letter(a):
                return True
        return False

    def first(self):
        return {
            a
            for a in self.formula.first()
            if isinstance(a, ProgramVariable) or self._lookahead_matches_letter(a)
        }

    def nullable(self) -> bool:
        return self.non_empty() and self.formula.nullable()

    @cached_str
    def __str__(self) -> str:
        return f"({self.formula} | {self.lookahead})"


class PrenexFormula(Formula):
    """
    Formula in prenex form -- we have quantifiers as a prefix
    of the formula, and thus we keep them separated.
    """

    def __init__(self, quantifiers: list, formula: Formula) -> None:
        super().__init__(quantifiers + [formula])
        self.quantifier_prefix = quantifiers
        self.formula = formula
        assert (
            self.formula.quantifiers() == []
        ), f"Quantifier-free part of prenex formula contains quantifiers: {self.formula}"

    def problems(self) -> List[str]:
        problems = []
        if self.formula.quantifiers():
            problems.append(
                f"Quantifier-free part of prenex formula contains quantifiers: {self.formula}"
            )
        tv = self.formula.trace_variables()
        if len(self.quantifier_prefix) != len(tv):
            problems.append(
                f"Number of quantifiers and trace variables do not match: "
                "are all quantifiers used or isn't there name shadowing?"
            )
        tv = set(tv)
        qs = set((q.var for q in self.quantifier_prefix))
        diff = qs.difference(tv)
        if diff:
            problems.append(f"Quantifiers {[str(d) for d in diff]} unused")
        diff = tv.difference(qs)
        if diff:
            problems.append(f"Free trace variables {[str(d) for d in diff]}")
        return super().problems() + problems

    def remove_stutter_reductions(self) -> Formula:
        return PrenexFormula(
            self.quantifier_prefix, self.formula.remove_stutter_reductions()
        )

    def functions(self) -> List["Function"]:
        return self.formula.functions()

    def substitute(self, S):
        return PrenexFormula(
            [t.substitute(S) for t in self.quantifiers()], self.formula.substitute(S)
        )

    @cached_str
    def __str__(self) -> str:
        return f"{' '.join(map(str, self.quantifier_prefix))}: {self.formula}"


class TraceFormula(Formula):
    """
    Part of HNL that describes trace properties
    """

    def derivative(self, wrt) -> DerivativesSet:
        raise NotImplementedError(f"derivative() not implemented for {self}")

    def nullable(self) -> bool:
        """
        Return True if the formula is nullable, i.e., if its language contains epsilon
        """
        return False

    def first(self) -> Set[Union["Constant", "ProgramVariable"]]:
        """
        Set of symbols that can be the first symbol in a word represented by this formula.
        NOTE: since we do not keep the alphabet with each formula,
        first() returns not only constants, but can return also program variables that stand
        for "any symbol the variable can have" which is typically any symbol from the alphabet.
        """
        raise NotImplementedError("first() not implemented for {self}")

    def non_empty(self):
        return self.first() != {}


class TraceVariable(TraceFormula):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def __str__(self) -> str:
        return str(self.name)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: "TraceVariable") -> bool:
        return isinstance(other, TraceVariable) and self.name == other.name

    def trace_variables(self) -> List["TraceVariable"]:
        return [self]

    def uniq_name(self) -> str:
        return str(self.name)


class Function(TraceFormula):
    def __init__(self, name: Token, traces) -> None:
        super().__init__()
        self.name = name
        assert all((map(lambda x: isinstance(x, TraceVariable), traces))), traces
        self.traces = traces

    @cached_str
    def __str__(self) -> str:
        return f"@{self.name}({', '.join(map(str, self.traces))})"

    def __hash__(self) -> int:
        return hash(str(self.name))

    def __eq__(self, other) -> bool:
        return isinstance(other, Function) and self.name == other.name

    def functions(self):
        return [self]

    def trace_variables(self) -> List[TraceVariable]:
        return self.traces

    def uniq_name(self) -> str:
        return f"{self.name}_{'_'.join(map(str, self.traces))}"


class Epsilon(TraceFormula):
    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Epsilon)

    def __hash__(self) -> int:
        return super().__hash__()

    def __str__(self) -> str:
        return "ε"

    def derivative(self, wrt) -> DerivativesSet:
        return DerivativesSet()

    def nullable(self) -> bool:
        return True

    def first(self) -> Set[Union["Constant", "ProgramVariable"]]:
        return set()


EPSILON = Epsilon()


class ProgramVariable(TraceFormula):
    def __init__(self, name: str, trace: TraceVariable) -> None:
        super().__init__()
        assert isinstance(trace, (TraceVariable, Function)), trace
        self.name: str = name
        self.trace: TraceVariable = trace

    def __eq__(self, other: Epsilon) -> bool:
        return (
            isinstance(other, ProgramVariable)
            and self.name == other.name
            and self.trace == other.trace
        )

    def __hash__(self) -> int:
        return (self.name, self.trace).__hash__()

    def trace_variables(self) -> List[TraceVariable]:
        if isinstance(self.trace, Function):
            return self.trace.trace_variables()
        return [self.trace]

    def program_variables(self) -> List["ProgramVariable"]:
        return [self]

    def program_variable_occurrences(self) -> List["ProgramVariable"]:
        return [self]

    def functions(self) -> List["Function"]:
        # Functions are inside the 'trace' variable
        return self.trace.functions()

    def derivative(self, wrt: "Constant") -> DerivativesSet:
        if wrt.is_rep() or not wrt.is_x():
            return DerivativesSet()
        return DerivativesSet(self)

    def nullable(self) -> bool:
        return True

    @cached_str
    def __str__(self) -> str:
        return f"{self.name}({self.trace})"

    def first(self) -> Set[Union["Constant", "ProgramVariable"]]:
        """
        Because we do not keep the alphabet with each formula,
        first() returns not only constants, but it can return also program variables that stand
        for "any symbol the variable can have" which is typically any symbol from the alphabet.
        """
        return {self}


class Constant(TraceFormula):
    NO_MARK = 0
    # constants marked with `x` represent letters read from the trace
    X_MARK = 1
    # Repetition of a constant -- this expression represents the _maximal_
    # possible repetition of a constant. It does not make sense for generation,
    # but it does make sense for derivatives -- derivative w.r.t rep(a) cuts off as many
    # a's from a word as possible.
    REP_MARK = 2
    REP_X_MARK = X_MARK | REP_MARK

    @classmethod
    def marks_combinations(cls):
        """
        Return iterable with all possible combinations of marks
        """
        return range(0, 2**Constant.REP_MARK)

    def __init__(self, value: str, marks=NO_MARK) -> None:
        super().__init__()
        assert isinstance(
            value, str
        ), f"Constant value is supposed to be a string, but got {value} : {type(value)}"
        self.value = value
        assert 0 <= marks <= 3, f"Unknown marks: {marks}"
        self.marks = marks

    def is_rep(self):
        return self.marks & Constant.REP_MARK

    def is_x(self):
        return self.marks & Constant.X_MARK

    def remove_marks(self):
        return Constant(self.value)

    def remove_mark(self, marks):
        return Constant(self.value, self.marks & ~marks)

    def remove_rep(self):
        return self.remove_mark(Constant.REP_MARK)

    def remove_x(self):
        return self.remove_mark(Constant.X_MARK)

    def with_marks(self, marks):
        return Constant(self.value, self.marks | marks)

    def with_rep(self):
        return self.with_marks(Constant.REP_MARK)

    def with_x(self):
        return self.with_marks(Constant.X_MARK)

    def with_rep_x(self):
        return self.with_marks(Constant.REP_X_MARK)

    def __eq__(self, other: "Constant") -> bool:
        return (
            isinstance(other, Constant)
            and self.value == other.value
            and self.marks == other.marks
        )

    def __hash__(self) -> int:
        return (self.value, self.marks).__hash__()

    def equiv(self, other):
        """
        Return True if constants are equivalent ignoring repetition/trace mark
        """
        assert isinstance(other, Constant), (other, type(other))
        return self.value == other.value

    def constants(self) -> List["Constant"]:
        return [self]

    def derivative(self, wrt: "Constant") -> DerivativesSet:
        if wrt.is_rep():
            return DerivativesSet()
        if wrt == self:
            return DerivativesSet(EPSILON)
        return DerivativesSet()

    @cached_str
    def __str__(self) -> str:
        return f"{self.value}{'⊕' if self.is_rep() else ''}{'ₓ' if self.is_x() else ''}"

    def first(self) -> Set[Union["Constant", "ProgramVariable"]]:
        return {self}

    def is_epsilon(self) -> bool:
        return False


class EpsilonConstant(Constant):
    """
    Constant used to represent epsilon transitions.
    """

    def __init__(self):
        super().__init__("")

    def is_epsilon(self) -> bool:
        return True

    def __hash__(self) -> int:
        return hash("__epsilon_constant__")

    def derivative(self, wrt: "Constant") -> DerivativesSet:
        raise RuntimeError("Cannot take derivative wrt epsilon")

    def __str__(self) -> str:
        return "ε"

    def first(self):
        raise RuntimeError(
            "EpsilonConstant should be used only for edges and there `first` makes no sense"
        )

    def constants(self):
        raise RuntimeError(
            "EpsilonConstant should be used only for edges and there `constants` makes no sense"
        )

    def equiv(self, other):
        """
        Return True if constants are equivalent ignoring repetition/trace mark
        """
        return isinstance(other, EpsilonConstant)

    def is_rep(self):
        return False

    def is_x(self):
        return False

    def remove_marks(self):
        return self

    def remove_mark(self, marks):
        return self

    def remove_rep(self):
        return self

    def remove_x(self):
        return self

    def with_marks(self, marks):
        raise RuntimeError("Not valid for this constant")

    def with_rep(self):
        raise RuntimeError("Not valid for this constant")

    def with_x(self):
        raise RuntimeError("Not valid for this constant")

    def with_rep_x(self):
        raise RuntimeError("Not valid for this constant")

    def __eq__(self, other) -> bool:
        return isinstance(other, EpsilonConstant)


EPSILON_CONSTANT = EpsilonConstant()
assert EpsilonConstant() == EpsilonConstant() == EPSILON_CONSTANT


class Concat(TraceFormula):
    def __init__(self, formula1: TraceFormula, formula2: TraceFormula) -> None:
        assert isinstance(formula1, TraceFormula), formula1
        assert isinstance(formula2, TraceFormula), formula1
        super().__init__([formula1, formula2])

    @cached_str
    def __str__(self) -> str:
        # if all(map(lambda c: isinstance(c, Constant), self.children)):
        #    return f"{self.children[0]}.{self.children[1]}"
        return f"({self.children[0]}.{self.children[1]})"

    def nullable(self) -> bool:
        return self.children[0].nullable() and self.children[1].nullable()

    def simplify(self) -> Formula:
        children = [self.children[0].simplify(), self.children[1].simplify()]
        if EPSILON == children[0]:
            return children[1]
        if EPSILON == children[1]:
            return children[0]
        return Concat(*children)

    def derivative(self, wrt: Constant) -> DerivativesSet:
        der = self.children[0].derivative(wrt)
        first_part = DerivativesSet(
            *(
                (
                    Concat(x, self.children[1])
                    if not isinstance(x, FormulaWithLookahead)
                    else FormulaWithLookahead(
                        Concat(x.formula, self.children[1]), x.lookahead
                    )
                )
                for x in der
            )
        )
        return first_part + (
            self.children[1].derivative(wrt)
            if self.children[0].nullable()
            else DerivativesSet()
        )

    def first(self) -> Set[Union[Constant, ProgramVariable]]:
        return (
            self.children[0]
            .first()
            .union(self.children[1].first() if self.children[0].nullable() else {})
        )


class Plus(TraceFormula):
    def __init__(self, formula1: TraceFormula, formula2: TraceFormula) -> None:
        assert isinstance(formula1, TraceFormula), formula1
        assert isinstance(formula2, TraceFormula), formula1
        super().__init__([formula1, formula2])

    @cached_str
    def __str__(self) -> str:
        return f"({self.children[0]} + {self.children[1]})"

    # def simplify(self):
    #    l = self.children[0].simplify()
    #    r = self.children[1].simplify()
    #    if l == EMPTY_SET:
    #        return r
    #    if r == EMPTY_SET:
    #        return l
    #    return Plus(l, r)

    def nullable(self):
        return self.children[0].nullable() or self.children[1].nullable()

    def derivative(self, wrt: Constant) -> DerivativesSet:
        return self.children[0].derivative(wrt) + self.children[1].derivative(wrt)

    def first(self) -> Set[Union[Constant, ProgramVariable]]:
        return self.children[0].first().union(self.children[1].first())


class Iter(TraceFormula):
    def __init__(self, formula: Constant) -> None:
        assert isinstance(formula, TraceFormula), formula
        super().__init__([formula])

    @cached_str
    def __str__(self) -> str:
        if isinstance(self.children[0], Constant):
            return f"{self.children[0]}*"
        return f"({self.children[0]})*"

    def derivative(self, wrt: Constant) -> DerivativesSet:
        return DerivativesSet(
            *(Concat(x, self) for x in self.children[0].derivative(wrt))
        )

    def nullable(self) -> bool:
        return True

    def simplify(self) -> Formula:
        return Iter(self.children[0].simplify())

    def first(self) -> Set[Union[Constant, ProgramVariable]]:
        return self.children[0].first()


class StutterReduce(TraceFormula):
    def __init__(self, formula: Formula) -> None:
        assert isinstance(formula, TraceFormula), formula
        super().__init__([formula])

    @cached_str
    def __str__(self) -> str:
        return f"⌊{self.children[0]}⌋"

    def nullable(self):
        return self.children[0].nullable()

    def simplify(self) -> Formula:
        c = self.children[0]
        while isinstance(c, StutterReduce):
            c = self.children[0]
        if isinstance(c, Constant) or c == EPSILON:
            return c
        return StutterReduce(c.simplify())

    def derivative(self, wrt: Constant) -> DerivativesSet:
        if not wrt.is_rep():
            return DerivativesSet()

        c_no_rep = wrt.remove_rep()
        c_unmarked = wrt.remove_marks()

        stutter_free_subformula = self.children[0].remove_stutter_reductions()
        reachable_derivatives = DerivativesSet()

        if wrt.is_x():
            for d in derivatives_fixpoint(stutter_free_subformula, wrt.remove_marks()):
                reachable_derivatives.update(derivatives_fixpoint(d, c_no_rep))

        reachable_derivatives.update(
            derivatives_fixpoint(stutter_free_subformula, c_no_rep)
        )

        return DerivativesSet(
            *(
                FormulaWithLookahead(StutterReduce(x), Not(c_unmarked))
                for x in reachable_derivatives
                if x.first() != {c_unmarked}
            )
        )

    def first(self) -> Set[Union[Constant, ProgramVariable]]:
        return self.children[0].first()


def derivatives_fixpoint(formula: TraceFormula, wrt: Constant) -> DerivativesSet:
    assert isinstance(wrt, Constant), type(wrt)
    result = formula.derivative(wrt)
    new_result = result + DerivativesSet(
        *(y for x in result for y in x.derivative(wrt))
    )
    while new_result != result:
        result = new_result
        new_result = result + DerivativesSet(
            *(y for x in result for y in x.derivative(wrt))
        )

    return result


class Quantifier(Formula):
    def __init__(self, var: TraceVariable, formula: Formula = None) -> None:
        """
        If the HNL formula is in prenex form, `formula` is None here.
        Otherwise, formula is an arbitrary, possibly quantified, formula.
        """
        super().__init__([formula] if formula is not None else [])
        self.var = var

    def quantifiers(self) -> List["Quantifier"]:
        return [self]

    def trace_variables(self) -> List[TraceVariable]:
        return [self.var]


class ForAll(Quantifier):
    def __init__(self, var: TraceVariable, formula: Formula = None) -> None:
        super().__init__(var, formula)

    @cached_str
    def __str__(self) -> str:
        if self.children:
            return f"∀{self.var}({self.children[0]})"
        return f"∀{self.var}"


class Exists(Quantifier):
    def __init__(self, var: TraceVariable, formula: Formula = None):
        super().__init__(var, formula)

    @cached_str
    def __str__(self):
        if self.children:
            return f"∃{self.var}({self.children[0]})"
        return f"∃{self.var}"


class Not(Formula):
    def __init__(self, formula: Formula) -> None:
        super().__init__([formula])

    @cached_str
    def __str__(self) -> str:
        return f"¬({self.children[0]})"


class And(Formula):
    def __init__(self, formula1: Formula, formula2: Formula):
        super().__init__([formula1, formula2])

    @cached_str
    def __str__(self):
        return f"({self.children[0]}) ∧ ({self.children[1]})"


class Or(Formula):
    def __init__(self, formula1: Formula, formula2: Formula):
        super().__init__([formula1, formula2])

    @cached_str
    def __str__(self):
        return f"({self.children[0]}) ∨ ({self.children[1]})"


class IsPrefix(Formula):
    def __init__(self, formula1: TraceFormula, formula2: TraceFormula) -> None:
        assert isinstance(formula1, TraceFormula), formula1
        assert isinstance(formula2, TraceFormula), formula1
        super().__init__([formula1, formula2])

    def is_simple(self) -> bool:
        # FIXME: we must check if the variables are not inside iteration
        return all((len(c.program_variable_occurrences()) <= 1 for c in self.children))

    def normalize(self) -> Formula:
        """
        Rename the left variable to `x` and the right variable to `y`.
        """
        lhs = self.children[0]
        rhs = self.children[1]
        lpv = lhs.program_variables()
        rpv = rhs.program_variables()
        assert len(lpv) <= 1, lpv
        assert len(rpv) <= 1, rpv
        if lpv:
            lhs = lhs.substitute({lpv[0]: ProgramVariable("x", TraceVariable("t"))})
        if rpv:
            rhs = rhs.substitute({rpv[0]: ProgramVariable("y", TraceVariable("t"))})

        return IsPrefix(lhs, rhs)

    @cached_str
    def __str__(self) -> str:
        return f"({self.children[0]} ≤ {self.children[1]})"
