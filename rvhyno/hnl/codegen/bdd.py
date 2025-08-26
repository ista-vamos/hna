from rvhyno.hnl.formula import Comparison, HLTLFormula


class ConstBDDNode:
    """Class for BDD which is either True or False"""

    def __init__(self, formula, bdd):
        self.formula = formula
        self.bddvar = bdd
        self.ltrace = None
        self.lvar = None
        self.rtrace = None
        self.rvar = None
        self.automaton = None

    def get_id(self):
        return 1


class BDDNode:
    _id_cnt = 0

    def __init__(self, formula: Comparison, bddvar):
        BDDNode._id_cnt += 1
        self._id = BDDNode._id_cnt
        self.formula = formula

        if isinstance(formula, Comparison):
            assert len(formula.children) == 2, formula.children
            self.lformula, self.rformula = formula.children
            self.original_formula = formula

            self.bddvar = bddvar
            # this automaton may be shared between multiple BDD nodes
            # if the automata for the nodes are isomorphic
            self.automaton = None
            # renaming of trace variables (mapping from unique names to original names)
            self.renaming = None
        else:
            assert isinstance(formula, HLTLFormula), formula

    def get_id(self):
        return self._id
