import logging
import sys
from os.path import isfile

from lark import Lark, logger

from formula import TraceFormula, RepConstant
from transformers import transform_ast


class LarkParser:
    def __init__(self, debug=False, start="start"):
        self._parser = Lark.open(
            "grammar.lark",
            rel_to=__file__,
            debug=debug,
            start=start,
        )
        if debug:
            logger.setLevel(logging.DEBUG)

    def parse_path(self, path):
        return self._parser.parse((open(path).read()))

    def parse_file(self, f):
        return self._parser.parse(f.read())

    def parse_text(self, text):
        return self._parser.parse(text)


class Parser(LarkParser):
    def parse_file(self, f):
        if isinstance(f, str):
            return transform_ast(super().parse_path(f))

        return transform_ast(super().parse_file(f))

    def parse_text(self, text):
        return transform_ast(super().parse_text(text))


def main():
    if len(sys.argv) != 2:
        print("Usage: parser.py [file|formula]", file=sys.stderr)
        sys.exit(1)

    parser = Parser()
    if isfile(sys.argv[1]):
        formula = parser.parse_path(sys.argv[1])
    else:
        formula = parser.parse_text(sys.argv[1])

    print("Formula: ", formula)
    print("Simplified:", formula.simplify())
    print("Removed stutter-red:", formula.remove_stutter_reductions())
    print("Formula again: ", formula)
    print("-----")
    print("Quantifiers: ", [str(q) for q in formula.quantifiers()])
    print("Trace variables: ", [str(t) for t in formula.trace_variables()])
    print("Program variables: ", [str(p) for p in formula.program_variables()])
    constants = formula.constants()
    print("Constants: ", [str(c) for c in constants])

    problems = formula.problems()
    if not formula.is_simple():
        problems.append("Formula is not simple, we require that for now")
    for problem in problems:
        print("\033[1;31m", problem, "\033[0m")
    if problems:
        exit(1)

    print("==================================================")
    print("All derivatives (empty are not shown):")

    def der(F):
        if not isinstance(F, TraceFormula):
            return
        print("-----")
        print(f"F = {F}")
        for c in constants:
            D = F.derivative(c)
            if not D.is_empty():
                print(f"F/{c} = {D}")
        for c in constants:
            D = F.derivative(RepConstant(c))
            if not D.is_empty():
                print(f"F/{RepConstant(c)} = {D}")
        print("-----")

    formula.visit(der)


if __name__ == "__main__":
    main()
