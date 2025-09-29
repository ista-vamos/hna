Usage
-----

TBD

Inputting transducers from files
-------------------------------

Symbolic hypernode logic allows to use custom data projection functions
(additionally to classical projections to values in the events).
We can specify these data functions with the parameter `--data-fun` and give
it a specification of a transducer that can be used as the data projection function on traces.

At this moment, the implementation supports transducers that do not use registers.

Another use of transducers (or automata in this case) is when we want to use a regular
expression on one side of comparison, but the expression is too complicated to write down.
In such a case, we can input this expression as an automaton in the same format as for transducers,
only it will read no traces. In the formula, you then use `{aut}` if the name of the automaton is "aut".
For example: `forall t: x(t) = {aut}` says that all x-projections of traces should be in the language of `aut`
that may be specified as:

```yaml
# file aut.yml
transducer:
  name: aut
  traces: []
  init: 0
  accept: a
  nodes: [0, 1, a]
  edges:
    - edge: 0 -> 1
      outputs: "'a'"
    - edge: 1 -> 0
      outputs: "'b'"
    - edge: 0 -> a
    - edge: 1 -> a
```
