# hna

Library for the construction, manipulation and runtime verification of hypernode automata

## Setup

#### Setup python virtual environment (required on newest systems).
```
python3 -mvenv /venv
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

And its done!


## Usage

Example of using the main script for HNL
```
./hnl.py 'forall t1, t2: (a+b).y(t1) <= [a.x(t2)]'
```
By default, the output is generated to `/tmp/hnl`. See `./hnl.py --help`.
To generate debugging files (e.g., the automata in GraphViz), use the `--debug`
flag. The debugging files will be stored into `dbg/` sub-directory in the output
directory.
