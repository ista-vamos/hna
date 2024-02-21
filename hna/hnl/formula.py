class Formula:
    """
    Formula of Hypernode Logic (HNL)
    """

    def __init__(self, children=None):
        self.children = children or []
        all(map(lambda x: isinstance(x, Formula), self.children)), children

    def quantifiers(self):
        """
        Return all quantifiers from the formula
        """
        return [t for c in self.children for t in c.quantifiers()]

    def trace_variables(self):
        """
        Get all trace variables from this formula
        """
        return list(set((t for c in self.children for t in c.trace_variables())))

    def program_variable_occurrences(self):
        """
        Get all occurences of trace variables from this formula
        """
        return [t for c in self.children for t in c.program_variable_occurrences()]

    def program_variables(self):
        """
        Get all trace variables from this formula
        """
        return list(set((t for c in self.children for t in c.program_variables())))

    def constants(self):
        """
        Get all constants used in this formula
        """
        return list(set((t for c in self.children for t in c.constants())))

    def problems(self):
        """
        Perform some well-definedness checks on the formula
        and return a list of problems that were found if any.
        """
        return []

    def visit_bottom_up(self, fn):
        """
        Visit recursively all children bottom up
        and call `fn(self)` for each visited formula.
        """
        for child in self.children:
            child.visit(fn)
        fn(self)

    def visit_top_down(self, fn):
        """
        Visit recursively all children top down
        and call `fn(self)` for each visited formula.
        """
        fn(self)
        for child in self.children:
            child.visit(fn)

    visit = visit_bottom_up

    def is_simple(self):
        """
        Return True if the formula is simple, i.e., it does not contain
        multiple program variables on either side of prefixing relation.
        """
        return all((c.is_simple() for c in self.children))

    def simplify(self):
        """
        Simpify the formula. This is not in-situ operation, it returns possibly a new object
        """
        return self


class PrenexFormula(Formula):
    """
    Formula in prenex form -- we have quantifiers as a prefix
    of the formula and thus we keep them separated.
    """

    def __init__(self, quantifiers: list, formula: Formula):
        super().__init__(quantifiers + [formula])
        self.quantifier_prefix = quantifiers
        self.formula = formula
        assert (
            self.formula.quantifiers() == []
        ), f"Quantifier-free part of prenex formula contains quantifiers: {self.formula}"

    def problems(self):
        problems = []
        if self.formula.quantifiers():
            problems.append(
                f"Quantifier-free part of prenex formula contains quantifiers: {self.formula}"
            )
        tv = self.formula.trace_variables()
        if len(self.quantifier_prefix) != len(tv):
            problems.append(
                f"Number of quantifiers and trace variables do not match: are all quantifiers used or isn't there name shadowning?"
            )
        tv = set(tv)
        qs = set((q.var for q in self.quantifier_prefix))
        D = qs.difference(tv)
        if D:
            problems.append(f"Quantifiers {[str(d) for d in D]} unused")
        D = tv.difference(qs)
        if D:
            problems.append(f"Free trace variables {[str(d) for d in D]}")
        return super().problems() + problems

    def __str__(self):
        return f"{' '.join(map(str, self.quantifier_prefix))}: {self.formula}"


class TraceFormula(Formula):
    """
    Part of HNL that describes trace properties
    """

    def derivative(self, wrt):
        raise NotImplementedError(f"derivative() not implemented for {self}")

    def nullable(self):
        """
        Return True if the formula is nullable, i.e., if its language contains epsilon
        """
        return False


class TraceVariable(TraceFormula):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def __str__(self):
        return str(self.name)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, TraceVariable) and self.name == other.name

    def trace_variables(self):
        return [self]


class ProgramVariable(TraceFormula):
    def __init__(self, name: str, trace: TraceVariable):
        super().__init__()
        assert isinstance(trace, TraceVariable), trace
        self.name = name
        self.trace = trace

    def __eq__(self, other):
        return (
            isinstance(other, ProgramVariable)
            and self.name == other.name
            and self.trace == other.trace
        )

    def __hash__(self):
        return (self.name, self.trace).__hash__()

    def trace_variables(self):
        return [self.trace]

    def program_variables(self):
        return [self]

    def program_variable_occurrences(self):
        return [self]

    def derivative(self, wrt):
        return ProgramVariable(f"{self.name}'", self.trace)

    def __str__(self):
        return f"{self.name}({self.trace})"


class Epsilon(TraceFormula):
    def __eq__(self, other):
        return isinstance(other, Epsilon)

    def __str__(self):
        return "ε"

    def derivative(self, wrt):
        return EMPTY_SET

    def nullable(self):
        return True


class EmptySet(TraceFormula):
    """
    Special trace formula representing empty set
    that we need because of derivatives
    """

    def __eq__(self, other):
        return isinstance(other, EmptySet)

    def __str__(self):
        return "∅"

    def derivative(self, wrt):
        return EMPTY_SET


EPSILON = Epsilon()
EMPTY_SET = EmptySet()


class Constant(TraceFormula):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def __eq__(self, other):
        return isinstance(other, Constant) and self.value == other.value

    def __hash__(self):
        return self.value.__hash__()

    def constants(self):
        return [self]

    def derivative(self, wrt):
        return Epsilon() if wrt == self else EmptySet()

    def __str__(self):
        return str(self.value)


class Concat(TraceFormula):
    def __init__(self, formula1, formula2):
        assert isinstance(formula1, TraceFormula), formula1
        assert isinstance(formula2, TraceFormula), formula1
        super().__init__([formula1, formula2])

    def __str__(self):
        # if all(map(lambda c: isinstance(c, Constant), self.children)):
        #    return f"{self.children[0]}.{self.children[1]}"
        return f"({self.children[0]}.{self.children[1]})"

    def nullable(self):
        return self.children[0].nullable() and self.children[1].nullable()

    def simplify(self):
        children = [self.children[0].simplify(), self.children[1].simplify()]
        if EPSILON == children[0]:
            return children[1]
        if EPSILON == children[1]:
            return children[0]
        if EMPTY_SET in children:
            return EMPTY_SET
        return Concat(*children)

    def derivative(self, wrt):
        d = self.children[0].derivative(wrt)
        return Plus(
            Concat(d, self.children[1]),
            self.children[1].derivative(wrt)
            if self.children[0].nullable()
            else EMPTY_SET,
        ).simplify()


class Plus(TraceFormula):
    def __init__(self, formula1, formula2):
        assert isinstance(formula1, TraceFormula), formula1
        assert isinstance(formula2, TraceFormula), formula1
        super().__init__([formula1, formula2])

    def __str__(self):
        return f"({self.children[0]} + {self.children[1]})"

    def simplify(self):
        l = self.children[0].simplify()
        r = self.children[1].simplify()
        if l == EMPTY_SET:
            return r
        if r == EMPTY_SET:
            return l
        return Plus(l, r)

    def nullable(self):
        return self.children[0].nullable() or self.children[1].nullable()

    def derivative(self, wrt):
        l, r = self.children[0].derivative(wrt), self.children[1].derivative(wrt)
        return Plus(l, r).simplify()


class Iter(TraceFormula):
    def __init__(self, formula):
        assert isinstance(formula, TraceFormula), formula
        super().__init__([formula])

    def __str__(self):
        if isinstance(self.children[0], Constant):
            return f"{self.children[0]}*"
        return f"({self.children[0]})*"

    def derivative(self, wrt):
        return Concat(self.children[0].derivative(wrt), self).simplify()

    def nullable(self):
        return True

    def simplify(self):
        return Iter(self.children[0].simplify())


class StutterReduce(TraceFormula):
    def __init__(self, formula):
        assert isinstance(formula, TraceFormula), formula
        super().__init__([formula])

    def __str__(self):
        return f"⌊{self.children[0]}⌋"

    def nullable(self):
        return self.children[0].nullable()

    def simplify(self):
        return Iter(self.children[0].simplify())


class Quantifier(Formula):
    def __init__(self, var: TraceVariable, formula: Formula = None):
        """
        If the HNL formula is in prenex form, `formula` is None here.
        Otherwise, formula is an arbitrary, possibly quantified, formula.
        """
        super().__init__([formula] if formula is not None else [])
        self.var = var

    def quantifiers(self):
        return [self]

    def trace_variables(self):
        return [self.var]


class ForAll(Quantifier):
    def __init__(self, var: TraceVariable, formula: Formula = None):
        super().__init__(var, formula)

    def __str__(self):
        if self.children:
            return f"∀{self.var}({self.children[0]})"
        return f"∀{self.var}"


class Exists(Quantifier):
    def __init__(self, var: TraceVariable, formula: Formula = None):
        super().__init__(var, formula)

    def __str__(self):
        if self.children:
            return f"∃{self.var}({self.children[0]})"
        return f"∃{self.var}"


class Not(Formula):
    def __init__(self, formula: Formula):
        super().__init__([formula])

    def __str__(self):
        return f"¬({self.children[0]})"


class And(Formula):
    def __init__(self, formula1: Formula, formula2: Formula):
        super().__init__([formula1, formula2])

    def __str__(self):
        return f"({self.children[0]}) ∧ ({self.children[1]})"


class Or(Formula):
    def __init__(self, formula1: Formula, formula2: Formula):
        super().__init__([formula1, formula2])

    def __str__(self):
        return f"({self.children[0]}) ∨ ({self.children[1]})"


class IsPrefix(Formula):
    def __init__(self, formula1: TraceFormula, formula2: TraceFormula):
        assert isinstance(formula1, TraceFormula), formula1
        assert isinstance(formula2, TraceFormula), formula1
        super().__init__([formula1, formula2])

    def is_simple(self):
        return all((len(c.program_variable_occurrences()) == 1 for c in self.children))

    def __str__(self):
        return f"({self.children[0]} ≤ {self.children[1]})"
