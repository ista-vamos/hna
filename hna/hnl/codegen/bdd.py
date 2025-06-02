from hna.hnl.formula import Comparison


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

        assert isinstance(formula, Comparison), formula
        self.formula = formula
        assert len(formula.children) == 2, formula.children
        l, r = formula.children
        l, r = l.program_variables(), r.program_variables()
        assert len(l) <= 1, l
        assert len(r) <= 1, r
        if l:
            l = l[0]
            self.ltrace = l.trace
            self.lvar = l.name
        else:
            self.ltrace = self.lvar = None

        if r:
            r = r[0]
            self.rtrace = r.trace
            self.rvar = r.name
        else:
            self.rtrace = self.rvar = None

        self.bddvar = bddvar
        # this automaton may be shared between multiple BDD nodes
        # if the automata for the nodes are isomorphic
        self.automaton = None

    def get_id(self):
        return self._id
