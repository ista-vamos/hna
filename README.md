# RVHyno

This tools generates monitors for hypernode logic and hypernode automata specifications.

## Setup

#### Setup python virtual environment (required on newer systems)

```
python3 -mvenv venv
```

#### Install python dependencies

```
# If you use Python virtual environment, this command
# must be run in every terminal in which you work with this project.
source venv/bin/activate

pip install -r requirements.txt
```

#### Configure and build

```
cmake . && make
```

And its done! If you want to run the tests, use `make test`.

#### Build configuration

```
pip install sphinx
cd docs && make html

# open _build/index.html
```

## Usage

See the documentation in `docs` (`docs/usage.rst` in particular).
If you built the HTML version (see above), then open `docs/_build/index.html`
in your browser.

### Hypernode logic

This project builds on the _extended hypernode logic (eHL)_ and extends it further,
so we call it only _hypernode logic_ and abbreviate it as _HNL_.

The `./hnl.py` script generates a C++ monitor for the given formula
and automatically compiles it. An example:

```
./hnl.py 'forall t1, t2: (a+b).y(t1) <= [a.x(t2)]'
```

If you want to browse the generated files, the output is generated to `/tmp/hnl`.
The generated code comes with CMake configuration and you can manually
change the configuration and recompile the monitor with

```
cd /tmp/hnl
cmake .
make
```

The script also generates some tests that can be run with `make check`.

To generate debugging files (e.g., the automata in GraphViz), use the `--debug`
flag. The debugging files will be stored into `dbg/` sub-directory in the output
directory. For other options, see `./hnl.py --help`.

If the traces are read from CSV files (the default and now the only option),
we assume one trace per file. Also, you need to specify the type of events
through `--data` and possibly the alphabet (values that can appear in the
events -- this is necessary only for the eHL logic):

```
./hnl.py 'forall t1, t2: (a+b).y(t1) <= [a.x(t2)]' --alphabet='a,b,c,d' --data='x: char, y: char'
```

The switch data is more flexible. You can specify that the data are atomic propositions.
`--data=aps: x, y` is a shortcut for `--data=x: bool, y: bool`.
Also, you can specify the range of data for each variable instead of giving an alphabet:
`--data: x : int [-5..5], y : unsigned [0..100]` (the limit values are included). Alternatively,
you can give the size of the numbers in bits: `--data: x: int [2b], y : short [1b]`.

If you need/want to give the explicit alphabet, you can use `--alphabet=Nb`  meaning that the alphabet
are N-bit numbers, e.g., `--alphabet=8b`.

#### References

- Chalupa, M., Henzinger, T.A., da Costa, A.O. (2025).
  [Monitoring Extended Hypernode Logic](https://link.springer.com/chapter/10.1007/978-3-031-76554-4_9) In: Integrated Formal Methods. IFM 2024

### Hypernode automata

The automata are given in the YAML format, an example automaton could be:

```yaml
automaton:
  init: q0
  nodes:
    q0: 'forall t1, t2: [x(t1)] <= [y(t2)]'
    q1: 'forall t1, t2: [x(t1)] <= y(t2)'
  edges:
    - edge: q0 -> q1
      action: act1
    - edge: q1 -> q1
      action: null
      # you can write the edge in different ways
    - edge: q0 q0
      action: null
    - edge: q1, q0
      action: act2
```

Run the script `./hna.py` to generate the monitor.

```
./hna.py automaton.yml
```

The output of the script is similar to the output of `hnl.py`: a C++ code with cmake configuration
that is stored into `/tmp/hna` (if not specified otherwise with `--out-dir`).
Similarly to `hnl.py`, you migh (need to) use the parameters `--csv-header`, `--alphabet`,
and `--debug`.

#### References

- Bartocci, Ezio and Henzinger, Thomas A. and Nickovic, Dejan and Oliveira da Costa, Ana (2023).
 [Hypernode Automata](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.CONCUR.2023.21). ArXiv.

## Troubleshooting

### Generting code is slow

The code generator is filled with different assertions, some of them are pretty
expensive. If you experience a problem with the speed of the code generation,
try running the scripts with `python -OO` or using PyPy.
