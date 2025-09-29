from . import SymbolicTransducer
from .labels import Constant, Var, Attr, Eps, Eq, NEq, TransitionMultiLabel
from rvhyno.automata.transition_system import State, Transition
from rvhyno.hnl.formula import TraceVariable


def parse_condition(cond, var, attrs):
    if not cond:
        return []

    terms = cond.split(",")
    cond = []
    for term in terms:
        lhs, op, rhs = term.split()
        lhs = Attr(var, lhs) if lhs in attrs else Constant(lhs)
        rhs = Attr(var, rhs) if rhs in attrs else Constant(rhs)
        if op in ("==", "="):
            Ctor = Eq
        elif op == "!=":
            Ctor = NEq
        cond.append(Ctor(lhs, rhs))
    return cond


def transducer_from_yaml(path, attrs):
    from yaml import safe_load
    from rvhyno.hna.parser.parser import parse_edge

    # FIXME: we assume only a single-tape transducer atm
    trace = TraceVariable("𝜏")

    attrs = set(x[0] for x in attrs)
    T = SymbolicTransducer(origin=path)

    with open(path, "r") as stream:
        data = safe_load(stream)
        for nd in data["transducer"]["nodes"]:
            T.add_state(State(str(nd)))
        for edge in data["transducer"]["edges"]:
            if edge.get("assignment"):
                raise NotImplementedError(
                    "The code does not support assignments in user functions yet"
                )

            source, target = parse_edge(edge["edge"])
            symbol = edge["symbol"]
            var = Var(symbol)
            output = edge["output"]
            if output == symbol:
                output = var
            elif output == r"\eps":
                output = Eps()
            else:
                Constant(output)

            T.add_transition(
                Transition(
                    T.get(str(source)),
                    TransitionMultiLabel(
                        {trace: var},
                        parse_condition(edge.get("condition"), var, attrs),
                        None,  # FIXME: no assignment yet
                        output,
                    ),
                    T.get(str(target)),
                )
            )

        T.add_init(T.get(str(data["transducer"]["init"])))
        for nd in data["transducer"]["accept"]:
            T.add_accepting(T.get(str(nd)))

        return str(data["transducer"]["name"]), T
