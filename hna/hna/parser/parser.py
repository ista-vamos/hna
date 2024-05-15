import logging

from lark import Lark, logger
from yaml import safe_load as yaml_load

from .transformers import transform_ast
from ..automaton import HyperNodeAutomaton, HypernodeState
from ...automata.automaton import Transition


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


def parse_edge(s):
    if "->" in s:
        tmp = s.split("->")
    elif "," in s:
        tmp = s.split(",")
    else:
        tmp = s.split()
    assert len(tmp) == 2, tmp
    return tmp[0].strip(), tmp[1].strip()


class YamlParser:

    def _parse_stream(self, stream):
        A = HyperNodeAutomaton()
        aut = yaml_load(stream)
        for node, formula in aut["automaton"]["nodes"].items():
            A.add_state(HypernodeState(node, formula))
        for edge in aut["automaton"].get("edges") or ():
            e = parse_edge(edge["edge"])
            A.add_transition(Transition(A.get(e[0]), edge["action"], A.get(e[1])))

        init = aut["automaton"]["init"]
        A.add_init(A.get(init))

        return A

    def parse_path(self, f):
        assert f, f
        if isinstance(f, str):
            with open(f, "r") as stream:
                return self._parse_stream(stream)
        return self._parse_stream(f)
