def path_is_accepting(A: "Automaton", path: list) -> bool:
    """
    Return if the path is accepting -- the last state
    must be accepting or from that state an accepting state
    must be reachable via epsilon steps.
    """
    state = path[-1].target
    states, wbg = set(), set()
    states.add(state)
    wbg.add(state)

    while wbg:
        state = wbg.pop()
        if A.is_accepting(state):
            return True
        # get all transitions from this state
        epsilonT = [
            t
            for _, tt in A.transitions(state, default=dict()).items()
            for t in tt
            if t.label.is_eps()
        ]
        priorities = list(set(t.priority for t in epsilonT))
        priorities.sort(reverse=True)

        # process epsilon transitions in the order of their priority
        for prio in priorities:
            T = [t for t in epsilonT if prio == t.priority]
            if T:
                for t in T:
                    if t.target not in states:
                        states.add(t.target)
                        wbg.add(t.target)
                break
    return False
