from lark import Transformer

from rvhyno.hnl.formula import *


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

    def is_eq(self, items):
        return IsEq(items[0], items[1])

    def stutter_reduce(self, items):
        return StutterReduce(items[0])

    def slice(self, items):
        if len(items) == 2:
            interval = int(items[1].value), int(items[1].value)
        else:
            assert len(items) == 3
            interval = int(items[1].value), int(items[2].value)
        return Slice(items[0], interval)

    def funcall(self, items):
        name = items[0].children[0].children[0]
        return Function(name, items[1:])

    def funtrace(self, items):
        return (items[0], items[1])

    def boolconst(self, items):
        assert len(items) == 1
        return items[0]

    def constint(self, items):
        assert len(items) == 1
        return Constant(items[0])

    def const_true(self, items):
        assert not items, items
        return TrivialTrue()

    def const_false(self, items):
        assert not items, items
        return Not(TrivialTrue())

    def quantifier(self, items):
        # our grammar assumes prenex form, so the quantifiers are just forall/exists and a name
        if items[0].data == "forall":
            return [ForAll(c) for c in items[0].children]
        elif items[0].data == "exists":
            return [Exists(c) for c in items[0].children]
        elif items[0].data == "exists_in_fun":
            fun = items[0].children[-1]
            return [ExistsFromFun(c, fun) for c in items[0].children[:-1]]
        elif items[0].data == "forall_in_fun":
            fun = items[0].children[-1]
            return [ForAllFromFun(c, fun) for c in items[0].children[:-1]]
        raise RuntimeError(f"Invalid quantifier: {items}")

    def quantified_formula(self, items):
        assert all(map(lambda i: isinstance(i, list), items[:-1])), items
        assert items[-1].data == "qf_formula", items

        quantifiers = []
        for qs in items[:-1]:
            assert all(map(lambda i: isinstance(i, Quantifier), qs)), qs
            quantifiers.extend(qs)

        return PrenexFormula(quantifiers, items[-1].children[0])

    def land(self, items):
        assert len(items) == 2, items
        return And(items[0], items[1])

    def lor(self, items):
        assert len(items) == 2, items
        return Or(items[0], items[1])

    def neg(self, items):
        assert len(items) == 1, items
        return Not(items[0])

    def hltl(self, items):
        print(items[0])
        return HLTLFormula(items[0])


def rec_concat(elem, rest):
    if not rest:
        return elem
    return Concat(elem, rec_concat(rest[0], rest[1:]))


def prnode(lvl, node, *args):
    print(" " * lvl * 2, node)


def transform_ast(lark_ast, ctx=None):
    # print(lark_ast.pretty())
    T = ProcessAST(lark_ast)
    return T.transform(lark_ast)
