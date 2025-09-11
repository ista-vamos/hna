import ctypes
from typing import Tuple

from rvhyno.utils import log
from rvhyno.hnl.formula import PrenexFormula, Constant


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
    log("dbg", "Split formula: topF = ", F1)
    log("dbg", "Split formula: subF = ", F2)
    log("dbg", "Same: ", same)

    return F1, F2, same


def c_type_info(ty: str) -> Tuple[int, int]:
    """
    Get information about system's C type: signess and byte-width.

    :return: a pair `(b, s)` where `s` is `True` iff the type is signed
             and `b` is the number of bytes the type takes.

    NOTE: the enumeration is not complete, fill in per need in the future.
    """
    bw = None
    signed = False

    if ty == "int":
        bw = ctypes.sizeof(ctypes.c_int)
        signed = True
    elif ty == "int8_t":
        bw = ctypes.sizeof(ctypes.c_int8)
        signed = True
    elif ty == "int32_t":
        bw = ctypes.sizeof(ctypes.c_int32)
        signed = True
    elif ty == "int64_t":
        bw = ctypes.sizeof(ctypes.c_int64)
        signed = True
    elif ty in ("uint", "unsigned int"):
        bw = ctypes.sizeof(ctypes.c_uint)
    elif ty == "uint32_t":
        bw = ctypes.sizeof(ctypes.c_uint32)
    elif ty == "uint64_t":
        bw = ctypes.sizeof(ctypes.c_uint64)
    elif ty in ("_Bool", "bool"):
        bw = ctypes.sizeof(ctypes.c_uint64)
    elif ty == "size_t":
        bw = ctypes.sizeof(ctypes.c_size_t)
    elif ty == "ssize_t":
        bw = ctypes.sizeof(ctypes.c_ssize_t)
        signed = True
    elif ty == "float":
        bw = ctypes.sizeof(ctypes.c_float)
        signed = True
    elif ty == "double":
        bw = ctypes.sizeof(ctypes.c_double)
        signed = True
    elif ty == "char":
        bw = ctypes.sizeof(ctypes.c_char)
        signed = True
    elif ty == "unsigned char":
        bw = ctypes.sizeof(ctypes.c_char)
    elif ty == "long":
        bw = ctypes.sizeof(ctypes.c_long)
        signed = True
    elif ty == "unsigned long":
        bw = ctypes.sizeof(ctypes.c_long)
    elif ty == "long long":
        bw = ctypes.sizeof(ctypes.c_longlong)
        signed = True
    elif ty == "unsigned long long":
        bw = ctypes.sizeof(ctypes.c_longlong)
        signed = True
    else:
        raise NotImplementedError(f"Unhandled C type: `{ty}`")

    return bw, signed


def c_type_bounds(ty: str) -> Tuple[int, int]:
    """
    Get C type's minimum and maximum value.

    The function assumes that the system is using two's complement.
    """
    bw, s = c_type_info(ty)
    if s:
        return -(2 << (8 * bw - 1)), 2 << (8 * bw - 1) - 1
    else:
        return 0, (2 ** (8 * bw)) - 1
