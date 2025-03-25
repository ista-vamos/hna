from hna.hnl.formula import PrenexFormula, ForAll, Not, Constant


def _same_quantifiers_prefix(formula: PrenexFormula):
    """
    Get a prefix of same quantifiers. For the purposes of this function,
    `forall` and `forall-from-fun` are different quantifiers.
    """
    assert isinstance(formula, PrenexFormula), formula

    quantifiers = formula.quantifier_prefix
    if not quantifiers:
        return [], []

    ty = quantifiers[0].quantifier_type()
    same, rest = [], []
    for n, q in enumerate(quantifiers):
        if q.quantifier_type() == ty:
            same.append(q)
        else:
            rest = formula.quantifier_prefix[n:]
            break

    return same, rest


def _split_formula(formula: PrenexFormula):
    """
    Split the given formula into a formula that has a prefix of the quantifiers up to the first
    alternation and the remaining subformula. The alternation includes not only existential alternation, but also
    from-function alternation. That is, the sequence of quantifiers 'forall t, forall t' in F' has an alternation.
    E.g., `forall a. exists b: F` gets transformed into
    two formulas: `forall a. F'` and `F' = exists b: F`.

    However, the first formula has only a placeholder constant instead of `F`,
    because we handle that part separately.

    \return first-formula, second-formula, same-quantifiers-prefix
    """
    same, rest = _same_quantifiers_prefix(formula)
    if not rest:
        # this formula is only universally quantified
        return formula, None, same

    F1 = PrenexFormula(same, Constant("subF"))
    F2 = PrenexFormula(rest, formula.formula)
    print("Split formula: topF = ", F1)
    print("Split formula: subF = ", F2)
    print("Same: ", same)

    return F1, F2, same
