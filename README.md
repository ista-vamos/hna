# HNA - Hypernode automata

Runtime verification of hypernode automata and (extended) hypernode logic.

## Setup

#### Setup python virtual environment (required on newer systems).
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

#### Checkout and build VAMOS
```
git submodule update --init
./build-vamos.sh -j4
```
Feel free to change the options in `./build-vamos.sh` if you need some extra
components to be built. If you are rebuilding VAMOS, it may be necessary
to do `cd vamos && make reset` before running `./build-vamos.sh`.

#### Configure and build

```
cmake . && make
```

And its done! If you want to run the tests, use `make test`.


## Usage

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

If the traces are read from CSV (the default and now the only option),
we assume one trace per file. Also, you need to specify the type of events
through `--csv-header` and possibly the alphabet (values that can appear in the
events):

```
./hnl.py 'forall t1, t2: (a+b).y(t1) <= [a.x(t2)]' --alphabet='a,b,c,d' --csv-header='x: char, y: char'
```

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

### Generting code is slow

The code generator is filled with different assertions, some of them are pretty expensive.
If you experience a problem with speed generation, try running the generators with `python -OO` or using PyPy.
