from functools import reduce

from lark import Transformer

from .formula import *


class ProcessAST(Transformer):
    def start(self, items):
        return items[0]

    def tracevar(self, items):
        return TraceVariable(items[0])

    def progvar(self, items):
        return ProgramVariable(items[0].children[0], items[1])

    def constant(self, items):
        return Constant(items[0])

    def seq(self, items):
        return rec_concat(items[0], items[1:])

    def concat(self, items):
        return rec_concat(items[0], items[1:])

    def iter(self, items):
        return Iter(items[0])

    def plus(self, items):
        return Plus(items[0], items[1])

    def is_prefix(self, items):
        return IsPrefix(items[0], items[1])

    def stutter_reduce(self, items):
        return StutterReduce(items[0])

    def quantifier(self, items):
        # our grammar assumes prenex form, so the quantifiers are just forall/exists and a name
        if items[0].data == "forall":
            return [ForAll(c) for c in items[0].children]
        elif items[0].data == "exists":
            return [Exists(c) for c in items[0].children]
        raise RuntimeError(f"Invalid quantifier: {items}")

    def quantified_formula(self, items):
        assert all(map(lambda i: isinstance(i, list), items[:-1])), items
        assert items[-1].data == "qf_formula", items

        quantifiers = []
        for qs in items[:-1]:
            assert all(map(lambda i: isinstance(i, Quantifier), qs)), qs
            quantifiers.extend(qs)

        return PrenexFormula(quantifiers, items[-1].children[0])


def rec_concat(elem, rest):
    if not rest:
        return elem
    return Concat(elem, rec_concat(rest[0], rest[1:]))


def prnode(lvl, node, *args):
    print(" " * lvl * 2, node)


def transform_ast(lark_ast, ctx=None):
    T = ProcessAST(lark_ast)
    return T.transform(lark_ast)
