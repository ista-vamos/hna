from . import SymbolicTransducer
from .labels import Constant, Var, Attr, Eps, Eq, NEq, TransitionMultiLabel, TraceFinished
from rvhyno.automata.transition_system import State, Transition
from rvhyno.hnl.formula import TraceVariable
from re import compile as re_compile


def parse_condition(terms, variables, traces, attrs):
    if not terms:
        return []

    cond = []

    # match the end predicate
    trace = '|'.join(traces.keys())
    regex = f'end\(({trace})\)'
    R_end = re_compile(regex)

    # match equality conditions
    attr='|'.join(attrs)
    var='|'.join(variables.keys())
    regex = f'(({attr})\(({var})\)|\d+)\s*(==|!=)\s*(({attr})\(({var})\)|\d+)'
    R = re_compile(regex)

    for term in terms:
        res = R_end.match(term)
        if res:
            cond.append(TraceFinished(traces[res.group(1)]))
            continue

        res = R.match(term)
        if not res:
            raise RuntimeError(f"Failed parsing the term `{term}` in condition. "
                               "This might not be your fault, this parser is not complete.")

        op = res.group(4)

        if res.group(1).isnumeric():
            lhs = Constant(res.group(1))
            assert res.group(2) is None, res.groups()
            assert res.group(3) is None, res.groups()
        else:
            assert res.group(2) is not None, res.groups()
            assert res.group(3) is not None, res.groups()
            lhs = Attr(variables[res.group(3)], res.group(2))

        if res.group(5).isnumeric():
            rhs = Constant(res.group(5))
            assert res.group(6) is None
            assert res.group(7) is None
        else:
            assert res.group(6) is not None
            assert res.group(7) is not None
            rhs = Attr(variables[res.group(7)], res.group(6))

        if op in ("==", "="):
            Ctor = Eq
        elif op == "!=":
            Ctor = NEq
        else:
            raise RuntimeError(f"Failed parsing the operation `{op}` in `{term}` in condition. "
                               "This might not be your fault, this parser is not complete.")
        cond.append(Ctor(lhs, rhs))
    return cond


def transducer_from_yaml(path, attrs):
    from yaml import safe_load
    from rvhyno.hna.parser.parser import parse_edge

    attrs = set(x[0] for x in attrs)
    T = SymbolicTransducer(origin=path)

    with (open(path, "r") as stream):
        data = safe_load(stream)
        transducer = data['transducer']

        traces = {t: TraceVariable(t) for t in transducer['traces']}
        for nd in transducer["nodes"]:
            T.add_state(State(str(nd)))
        for edge in transducer["edges"]:
            if edge.get("assignment"):
                raise NotImplementedError(
                    "The code does not support assignments in user functions yet"
                )

            source, target = parse_edge(edge["edge"])
            symbols = {}
            variables = {}
            reads = edge["reads"].items() if 'reads' in edge else ()
            for tr, var in reads:
                if tr in symbols:
                    raise RuntimeError(f"An edge reads {tr} more than once: {edge}")
                if var in variables:
                    raise RuntimeError(f"Variable {var} read from multiple traces: {edge}")
                if tr not in traces:
                    raise RuntimeError(f"Unknown trace {tr} in `{edge}`")

                v = Var(var)
                variables[var] = v
                symbols[traces[tr]] = v

            output = edge.get("outputs")
            if output is None or output == r"\eps":
                output = Eps()
            elif output in variables:
                output = variables[output]
            else:
                output = Constant(output)

            cond = edge.get("condition")
            if cond:
                if not isinstance(cond, list):
                    cond = [t.strip() for t in cond.split("&&")]
            T.add_transition(
                Transition(
                    T.get(str(source)),
                    TransitionMultiLabel(
                        symbols,
                        parse_condition(cond, variables, traces, attrs),
                        None, # FIXME: no assignment yet
                        output,
                    ),
                    T.get(str(target)),
                )
            )

        init = T.get(str(transducer["init"]))
        acc = T.get(str(transducer["accept"]))
        assert init
        assert acc
        T.add_init(init)
        T.add_accepting(acc)

        return str(transducer["name"]), T
