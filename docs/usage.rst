Usage
-----

TBD

Inputting transducers from files
-------------------------------

Symbolic hypernode logic allows to use custom data projection functions
(additionally to classical projections to values in the events).
We can specify these data functions with the parameter `--data-fun` and give
it a specification of a transducer that can be used as the data projection function on traces.

At this moment, the implementation supports only single-tape transducers
that do not use registers.
