import logging
import sys
from os.path import isfile

from lark import Lark, logger

from . formula import TraceFormula, IsPrefix, Constant
from . transformers import transform_ast
from . formula2automata import formula_to_automaton, compose_automata


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


counter = 0


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

    # print("==================================================")
    # print("All derivatives (empty are not shown):")

    # def der(F):
    #    if not isinstance(F, TraceFormula):
    #        return
    #    print("-----")
    #    print(f"F = {F}")
    #    for c in (x.with_marks(marks) for x in constants for marks in Constant.marks_combinations()):
    #        D = F.derivative(c)
    #        if not D.is_empty():
    #            print(f"F/{c} = {D}")
    #    print("-----")

    # formula.visit(der)

    from hna.codegen.hnl import CodeGenCpp
    cg = CodeGenCpp()
    cg.generate(formula)

    def aut(F):
        if not isinstance(F, IsPrefix):
            return
        print("-----")
        print(f"F = {F}")

        alphabet = F.constants()
        A1 = formula_to_automaton(F.children[0], alphabet)
        global counter
        counter += 1
        print(f"Output to : /tmp/F-{counter}.dot")
        with open(f"/tmp/F-{counter}.dot", "w") as f:
            A1.to_dot(f)

        A2 = formula_to_automaton(F.children[1], alphabet)
        counter += 1
        print(f"Output to : /tmp/F-{counter}.dot")
        with open(f"/tmp/F-{counter}.dot", "w") as f:
            A2.to_dot(f)

        counter += 1
        print(f"COMPOSE Output to : /tmp/F-{counter}.dot")
        with open(f"/tmp/F-{counter}.dot", "w") as f:
            compose_automata(A1, A2).to_dot(f)

        print("-----")

    formula.visit(aut)


if __name__ == "__main__":
    main()
