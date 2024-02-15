from os.path import isfile
import logging
import sys

from lark import Lark, logger

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

    print(formula)


if __name__ == "__main__":
    main()
