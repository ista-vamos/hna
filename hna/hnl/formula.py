class Formula:
    """
    Formula of Hypernode Logic (HNL)
    """
    def __init__(self, children=None):
        self.children = children or []
        all(map(lambda x: isinstance(x, Formula), self.children)), children

class PrenexFormula(Formula):
    """
    Formula in prenex form -- we have quantifiers as a prefix
    of the formula and thus we keep them separated.
    """
    def __init__(self, quantifiers: list, formula: Formula):
        super().__init__(quantifiers + [formula])
        self.quantifiers = quantifiers
        self.formula = formula

    def __str__(self):
        return f"{' '.join(map(str, self.quantifiers))}: {self.formula}"

class TraceFormula(Formula):
    """
    Part of HNL that describes trace properties
    """

class TraceVariable(TraceFormula):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def __str__(self):
        return str(self.name)


class ProgramVariable(TraceFormula):
    def __init__(self, name: str, trace: TraceVariable):
        super().__init__()
        assert isinstance(trace, TraceVariable), trace
        self.name = name
        self.trace = trace

    def __str__(self):
        return f"{self.name}({self.trace})"
class Constant(TraceFormula):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def __eq__(self, other):
        return self.value == other.value

    def __str__(self):
        return str(self.value)

class Concat(TraceFormula):
    def __init__(self, formula1, formula2):
        assert isinstance(formula1, TraceFormula), formula1
        assert isinstance(formula2, TraceFormula), formula1
        super().__init__([formula1, formula2])

    def __str__(self):
       #if all(map(lambda c: isinstance(c, Constant), self.children)):
       #    return f"{self.children[0]}.{self.children[1]}"
        return f"({self.children[0]}.{self.children[1]})"
class Plus(TraceFormula):
    def __init__(self, formula1, formula2):
        assert isinstance(formula1, TraceFormula), formula1
        assert isinstance(formula2, TraceFormula), formula1
        super().__init__([formula1, formula2])

    def __str__(self):
        return f"({self.children[0]} + {self.children[1]})"

class Iter(TraceFormula):
    def __init__(self, formula):
        assert isinstance(formula, TraceFormula), formula
        super().__init__([formula])

    def __str__(self):
        if isinstance(self.children[0], Constant):
            return f"{self.children[0]}*"
        return f"({self.children[0]})*"


class StutterReduce(TraceFormula):
    def __init__(self, formula):
        assert isinstance(formula, TraceFormula), formula
        super().__init__([formula])

    def __str__(self):
        return f"⌊{self.children[0]}⌋"

class Quantifier(Formula):
    def __init__(self, var: TraceVariable, formula: Formula = None):
        """
        If the HNL formula is in prenex form, `formula` is None here.
        Otherwise, formula is an arbitrary, possibly quantified, formula.
        """
        super().__init__([formula] if formula is not None else [])
        self.var = var
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

    def __str__(self):
        return f"({self.children[0]} ≤ {self.children[1]})"