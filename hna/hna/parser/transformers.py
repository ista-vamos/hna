from lark import Transformer


class ProcessAST(Transformer):
    def start(self, items):
        return items[0]


def prnode(lvl, node, *args):
    print(" " * lvl * 2, node)


def transform_ast(lark_ast, ctx=None):
    T = ProcessAST(lark_ast)
    return T.transform(lark_ast)
