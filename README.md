# RVHyno

This tools generates monitors for hypernode logic and hypernode automata specifications.

## Setup

#### Install python dependencies

```sh
uv sync
```

With some compiler versions, the command may fail with an error like this:

```sh
thirdparty/espresso/src/cofactor.c:351:50: error: incompatible function pointer types passing 'int (set **, set **)' (aka 'int (unsigned int **, unsigned int **)') to parameter of type 'int (*
_Nonnull)(const void *, const void *)' [-Wincompatible-function-pointer-types]
  351 |     qsort((char *) (T+2), ncubes, sizeof(set *), d1_order);
      |                                                  ^~~~~~~~
/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/_stdlib.h:181:22: note: passing argument to parameter '__compar' here
  181 |             int (* _Nonnull __compar)(const void *, const void *));
      |                             ^
1 error generated.
error: command '/usr/bin/cc' failed with exit code 1
```

If that happens, run instead:

```sh
CFLAGS="-Wno-incompatible-function-pointer-types" uv sync
```

#### Configure and build

```sh
cmake . && make
```

And its done! If you want to run the tests, use `make test`.

#### Build documentation

This will build the documentation in HTML:

```sh
pip install sphinx
make doc

# open _build/index.html
```

The documentation is built in `docs/_build` directory. Whenever you want to
re-build the documentation, just run `make doc` (provided you have already
installed `sphinx`).

## Usage

See the documentation in `docs` (`docs/usage.rst` in particular).
If you built the HTML version (see above), then open `docs/_build/index.html`
in your browser.

### Hypernode logic

This project builds on the _extended hypernode logic (eHL)_ and extends it further,
so we call it only _hypernode logic_ and abbreviate it as _HNL_.

The `./hnl.py` script generates a C++ monitor for the given formula
and automatically compiles it. An example:

```sh
uv run ./hnl.py 'forall t1, t2: (a+b).y(t1) <= [a.x(t2)]'
```

If you want to browse the generated files, the output is generated to `/tmp/hnl`.
The generated code comes with CMake configuration and you can manually
change the configuration and recompile the monitor with

```sh
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

```sh
uv run ./hnl.py 'forall t1, t2: (a+b).y(t1) <= [a.x(t2)]' --alphabet='a,b,c,d' --data='x: char, y: char'
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

```sh
./hna.py automaton.yml
```

The output of the script is similar to the output of `hnl.py`: a C++ code with cmake configuration
that is stored into `/tmp/hna` (if not specified otherwise with `--out-dir`).
Similarly to `hnl.py`, you migh (need to) use the parameters `--csv-header`, `--alphabet`,
and `--debug`.

#### References

- Bartocci, Ezio and Henzinger, Thomas A. and Nickovic, Dejan and Oliveira da Costa, Ana (2023).
 [Hypernode Automata](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.CONCUR.2023.21). ArXiv.

## Setup without uv (legacy)

#### Setup python virtual environment (required on newer systems)

```
python3 -mvenv venv
```

#### Install python dependencies

```sh
# If you use Python virtual environment, this command
# must be run in every terminal in which you work with this project.
source venv/bin/activate

pip install -r requirements.txt
```

Before using scripts, always activate the virtual environment (required in every terminal you work in)
if it hasn't been done yet:

```sh
source venv/bin/activate
```

## Troubleshooting

### Generating code is slow

The code generator is filled with different assertions, some of them are pretty
expensive. If you experience a problem with the speed of the code generation,
try running the scripts with `python -OO` or using PyPy or Codon.
