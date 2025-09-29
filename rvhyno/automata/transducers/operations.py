from copy import copy

from rvhyno.automata.transducers import SymbolicTransducer
from rvhyno.automata.transducers.labels import (
    TransitionMultiLabel,
    TraceFinished,
    Eq,
    Constant,
    NEq,
)
from rvhyno.automata.transition_system import Transition, State
from rvhyno.hnl.formula import TraceVariable


def concat_transducers(left: SymbolicTransducer, right: SymbolicTransducer):
    T, renamed_states = merge_transducers(left, right)
    # set new initial and accepting states
    for s in left.initial_states():
        T.add_init(s)
    for s in right.accepting_states():
        T.add_accepting(renamed_states.get(s, s))

    for l_acc, r_init in (
        (a, i) for a in left.accepting_states() for i in right.initial_states()
    ):
        T_r_init = renamed_states.get(r_init, r_init)
        for out in (t for vals in T.transitions(T_r_init).values() for t in vals):
            T.add_transition(Transition(l_acc, out.label, out.target))
            if right.is_accepting(r_init):
                T.add_accepting(l_acc)

    return T


def union_transducers(
    left: SymbolicTransducer, right: SymbolicTransducer
) -> SymbolicTransducer:
    T, renamed_states = merge_transducers(left, right)
    # set new accepting states
    for s in left.accepting_states():
        T.add_accepting(s)
    for s in right.accepting_states():
        T.add_accepting(renamed_states.get(s, s))

    new_init = add_new_init(T)

    for old_init in left.initial_states():
        for out in T.transitions_from(old_init):
            T.add_transition(Transition(new_init, out.label, out.target))
            if left.is_accepting(old_init):
                T.add_accepting(new_init)
    for old_init in right.initial_states():
        old_init_r = renamed_states.get(old_init, old_init)
        for out in T.transitions_from(old_init_r):
            T.add_transition(Transition(new_init, out.label, out.target))
            if right.is_accepting(old_init):
                T.add_accepting(new_init)

    return T


def add_new_init(T):
    # find an unused new init name
    new_init_name = "0"
    while T.get(new_init_name) is not None:
        new_init_name += "0"
    new_init = State(new_init_name)
    T.add_state(new_init)
    T.add_init(new_init)
    return new_init


def merge_transducers(left, right):
    """
    Merge two transducers into a single transducer, renaming states of 'right' if the names conflict.
    That is, do a disjoint union.
    Also, clean initial and accepting states.
    """

    if left.registers() and right.registers():
        raise NotImplementedError("Rename conflicting registers")

    registers = ((left.registers() or []) + (right.registers() or [])) or None
    # we might need to rename states, keep the new names in this map
    renamed_states = {}
    renamed_registers = {}
    states = left.states().copy()
    # FIXME: this might be inefficient
    for r_state in right.states():
        if r_state in states:
            new_state = State(f"{r_state.name()}'")
            renamed_states[r_state] = new_state
            r_state = new_state
        states.append(r_state)
    transitions = left.transitions().copy()
    if not renamed_states:
        transitions += right.transitions()
    else:
        for rt in right.transitions():
            source, target = rt.source, rt.target
            transitions.append(
                Transition(
                    renamed_states.get(source, source),
                    rt.label,
                    renamed_states.get(target, target),
                )
            )
    T = SymbolicTransducer(
        states=states,
        registers=registers,
        transitions=transitions,
    )
    return T, renamed_states


def remove_epsilon_steps(eT: SymbolicTransducer) -> SymbolicTransducer:
    """Return the transducer `eT` without epsilon steps"""

    transitions = []
    accepting = []
    for trans in eT.transitions():
        if not trans.label.is_eps():
            transitions.append(trans)
            continue

        TT = eT.transitions(trans.target)
        TT = TT.items() if TT else ()
        for _, target_out in TT:
            for trans_out in target_out:
                assert isinstance(trans_out, Transition), trans_out
                if trans.source == trans_out.target and trans_out.label.is_eps():
                    # don't add \eps self-loops
                    continue

                transitions.append(Transition(trans.source, trans_out.label, trans_out.target))
                if eT.is_accepting(trans.target):
                    accepting.append(trans.source)

    return SymbolicTransducer(
        states=eT.states(),
        registers=eT.registers(),
        transitions=transitions,
        init_states=eT.initial_states(),
        accepting_states=eT.accepting_states() + accepting,
        origin=eT.origin(),
    )



def iterate_transducer(T1: SymbolicTransducer) -> SymbolicTransducer:
    assert T1 is not None
    T = T1.copy(new_origin=T1)
    for acc, init in (
        (o, i) for o in T1.accepting_states() for i in T1.initial_states()
    ):
        for init_out in (
            t for vals in T1.transitions(init, default=()).values() for t in vals
        ):
            assert isinstance(init_out, Transition), (init_out, type(init_out))
            T.add_transition(Transition(acc, init_out.label, init_out.target))
            if T1.is_accepting(init):
                T.add_accepting(acc)

    # also, we must make sure we accept the empty word
    # check if the initial states are accepting
    if not all(T.is_accepting(s) for s in T.initial_states()):
        # check if we can just mark the states accepting -- that we can do if they have no
        # incoming edges
        if all(not T.transitions_to(s) for s in T.initial_states()):
            for s in T.initial_states():
                T.add_accepting(s)
        else:
            # we must add a new initial state that accepts epsilon and then continues to T
            # (basically the union with a transducer that accepts epsilon)
            new_init = add_new_init(T)
            T.add_accepting(new_init)
            for old_init in T1.initial_states():
                for out in T.transitions_from(old_init):
                    T.add_transition(Transition(new_init, out.label, out.target))

    return T


def _check_transducers_for_composition(inner, outer) -> None:
    if set(inner.traces).intersection(set(outer.traces)):
        with open("/tmp/inner.dot", "w") as f:
            inner.to_dot(f)
        with open("/tmp/outer.dot", "w") as f:
            outer.to_dot(f)
        raise RuntimeError("`inner` and `outer` have a common trace")

    if inner.has_eps_transitions():
        with open("/tmp/inner.dot", "w") as f:
            inner.to_dot(f)
        raise RuntimeError(
            "Transducers in the composition cannot have epsilon transitions (see /tmp/inner.dot)"
        )
    if outer.has_eps_transitions():
        with open("/tmp/outer.dot", "w") as f:
            outer.to_dot(f)
        raise RuntimeError(
            "Transducers in the composition cannot have epsilon transitions (see /tmp/outer.dot)"
        )

    # with open("/tmp/inner.dot", "w") as f:
    #    inner.to_dot(f)
    # with open("/tmp/outer.dot", "w") as f:
    #    outer.to_dot(f)


def compose_transducers(
    inner: SymbolicTransducer, outer: SymbolicTransducer, on: TraceVariable, origin=None
) -> SymbolicTransducer:
    """
    Compute the sequential composition `outer(inner)` where the output of `inner`
    is fed to `outer` into the trace `on`.
    """

    if __debug__:
        _check_transducers_for_composition(inner, outer)

    # pairs of states that we will later translate to State. But for now, it is more comfortable
    # to work with pairs of states.
    states = set()
    # triple (source, label, target) where source and target are pairs of states.
    # We will later translate them into Transition classes
    transitions = []
    queue = [(ii, oi) for ii in inner.initial_states() for oi in outer.initial_states()]
    new_queue = []

    while queue:
        for state_pair in queue:
            # print(f"CUR: {state_pair[0]},{state_pair[1]}")
            if state_pair in states:
                continue
            states.add(state_pair)

            # handle input-epsilon steps of outer transducer
            for outer_t in outer.transitions_from(state_pair[1]):
                if outer_t.label.is_input_eps():
                    new_target = (state_pair[0], outer_t.target)
                    label = outer_t.label

                    transitions.append(
                        (
                            state_pair,  # TransitionMultiLabel(label.symbols, condition, assign,
                            #                     label.output.subst(subst)),
                            label,
                            new_target,
                        )
                    )
                    new_queue.append(new_target)

            # handle output-epsilon steps of the inner transducer
            for inner_t in inner.transitions_from(state_pair[0]):
                if inner_t.label.is_output_eps():
                    new_target = (inner_t.target, state_pair[1])
                    transitions.append((state_pair, inner_t.label, new_target))
                    new_queue.append(new_target)

            for inner_t, outer_t in (
                (it, ot)
                for it in inner.transitions_from(state_pair[0])
                for ot in outer.transitions_from(state_pair[1])
            ):
                if outer_t.label.is_input_eps() or inner_t.label.is_output_eps():
                    # these were handled separately
                    continue

                # combine the transitions
                new_t = compose_transitions(inner_t, outer_t, on)
                if new_t is None:
                    # the transition had UNSAT condition
                    continue
                assert new_t[0] == state_pair
                assert new_t[0] == (inner_t.source, outer_t.source)
                assert new_t[2] == (inner_t.target, outer_t.target)
                # print(
                #    f"NEW_T: {new_t[0][0]},{new_t[0][1]} - {new_t[1]} -> {new_t[2][0]},{new_t[2][1]}"
                # )
                transitions.append(new_t)
                # new_t[2] is the target of the new to-be-transition
                if new_t[2] not in states:
                    new_queue.append(new_t[2])

        queue, new_queue = new_queue, []

    states = {(i, o): State(f"({i},{o})") for (i, o) in states}

    registers = inner.registers()
    registers = (
        outer.registers() if not registers else (registers + (outer.registers() or []))
    )
    return SymbolicTransducer(
        states=list(states.values()),
        registers=registers,
        transitions=[Transition(states[t[0]], t[1], states[t[2]]) for t in transitions],
        init_states=[
            states[s]
            for s in states.keys()
            if inner.is_initial(s[0]) and outer.is_initial(s[1])
        ],
        accepting_states=[
            states[s]
            for s in states.keys()
            if inner.is_accepting(s[0]) and outer.is_accepting(s[1])
        ],
        origin=origin,
    )


def compose_transitions(
    inner: Transition, outer: Transition, on: TraceVariable
) -> Transition:
    inner_l: TransitionMultiLabel = inner.label
    outer_l: TransitionMultiLabel = outer.label

    symbols = inner_l.symbols.copy()
    symbols.update(outer_l.symbols)
    del symbols[on]

    output_l = inner_l.output
    assert not output_l.is_eps(), inner_l
    subst = (outer_l.symbols[on], output_l)
    condition = simplify_condition(
        inner_l.condition + substitute_lst(outer_l.condition, subst)
    )

    if condition is None:  # UNSAT condition
        return None

    label = TransitionMultiLabel(
        symbols=symbols,
        condition=condition,
        assign=(
            (inner_l.assignment or []) + substitute_lst(outer_l.assignment or [], subst)
        )
        or None,
        output=outer_l.output.subst(subst),
    )

    return (inner.source, outer.source), label, (inner.target, outer.target)


def normalize_term(term):
    """
    Any variable is 'smaller' than any register, and any register is smaller than any constant.
    Variables, registers, and constants are ordered lexicographically.
    This function outputs the smaller of (term.lhs, term.rhs) or (term.rhs, term.lhs).
    NOTE: it modifies the original term!
    """
    if isinstance(term, TraceFinished):
        return term
    if not term.lhs < term.rhs:
        term.rhs, term.lhs = term.lhs, term.rhs
    return term


def remove_duplicates(cond):
    return list(set(normalize_term(c) for c in cond))


def remove_trivial(cond):
    return [c for c in cond if not isinstance(c, Eq) or c.lhs != c.rhs]


def get_eq_constants(eq_classes):
    consts = {}
    for eqcl in eq_classes.values():
        constants = [elem for elem in eqcl if isinstance(elem, Constant)]
        if len(constants) > 1:
            return None  # two different constants should equal
        elif not constants:
            continue

        for elem in eqcl:
            if isinstance(elem, Constant):
                continue
            assert (elem not in consts) or consts[elem] == constants[0], (
                eq_classes,
                constants,
                consts,
            )
            consts[elem] = constants[0]

    return consts


def propagate_constants(cond, consts):
    for s in consts.items():
        cond = substitute_lst(cond, s)
    cond += [Eq(x, c) for x, c in consts.items()]
    return remove_trivial(remove_duplicates(cond))


def simplify_condition(cond):
    # remove repeated terms
    cond = remove_duplicates(cond)
    cond = remove_trivial(cond)

    # TODO: do this properly with SMT solver? Or SymPy?
    eq_classes = get_eq_classes(cond)

    consts = get_eq_constants(eq_classes)
    if consts is None:
        # UNSAT condition, two different constants should equal
        return None

    for c in (c for c in cond if isinstance(c, NEq)):
        if c.rhs in eq_classes.get(c.lhs, ()):
            # UNSAT condition, there's a claim that two elements
            # should be the same and different at the same time
            return None

    cond = propagate_constants(cond, consts)

    return cond


def get_eq_classes(cond):
    eq_classes = {}
    for c in (x for x in cond if isinstance(x, Eq)):
        # FIXME: this is not very efficient, but we'll not likely have problem with this
        C1 = eq_classes.setdefault(c.lhs, set((c.lhs,)))
        C2 = eq_classes.setdefault(c.rhs, set((c.rhs,)))
        assert c.lhs in C1
        assert c.rhs in C2
        C = C1.union(C2)
        for x in C:
            eq_classes[x] = C
    return eq_classes


def substitute_lst(lst, subst):
    return [x.subst(subst) for x in lst]


def substitute_trace(eT: SymbolicTransducer, old: TraceVariable, new: TraceVariable) -> SymbolicTransducer:
    """Return the transducer `eT` where trace variable `old` has been replaced by `new`"""

    transitions=[]
    for trans in eT.transitions():
        label = trans.label
        symbols = label.symbols.copy()
        if old in symbols:
            symbols[new] = symbols[old]
            del symbols[old]
        condition = [c.subst((old, new)) for c in label.condition]
        transitions.append(Transition(trans.source,
                                      TransitionMultiLabel(symbols, condition, label.assignment, label.output),
                                      trans.target)
        )
    T = SymbolicTransducer(
        states=eT.states(),
        registers=eT.registers(),
        transitions=transitions,
        init_states=eT.initial_states(),
        accepting_states=eT.accepting_states(),
        origin=eT.origin(),
    )

    return T
