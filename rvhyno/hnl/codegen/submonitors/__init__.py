"""
Code generation for sub-monitors (nested monitors) of the top-level monitor.

Sub-monitors are of two types:
 - _atom monitors_: these take a universally quantified atom formula
   (with no other quantifiers than those universal),
   and a set of traces that should be instantiated into the quantifiers,
   and a list of fixed traces that are used for free variables in the formula,
   and evaluate the given atom formula over the given traces.
 - _sub-formula monitors_ that take a formula F with quantifiers and
   instantiate (a prefix of) the quantifiers with traces from a given set of traces.
   For each instantiation of the traces a sub-monitor of F where the instantiated
   traces are fixed is created and monitored for the result by this monitor.
   This monitor also takes a list of fixed traces for free variables in the formula
   and propagates it to the sub-monitor.

Look for examples of breaking down the monitoring task into sub-monitors in the
documentation.

FIXME: cross-ref

HyperLTL
---------

We support HyperLTL monitoring through employing RVHyper as the "atom monitor".

FIXME: TBD
"""
