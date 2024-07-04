#!/usr/bin/env python3

import sys
import csv

from subprocess import Popen, PIPE, TimeoutExpired
from os.path import abspath, dirname, join as pathjoin
from tempfile import mkdtemp
from shutil import rmtree
from os import chdir, makedirs, listdir
from random import randrange
from statistics import mean, stdev

from traces import *

SRCDIR = f"{dirname(sys.argv[0])}/../"
HNA_SCRIPT = f"{SRCDIR}/hna.py"
TRIALS = 10  # how many times run the monitor on a given input


def err(msg):
    print(msg, file=sys.stderr)
    exit(1)


def runcmd(cmd, timeout=None, no_capture=False):

    is_timeout = False
    if no_capture:
        proc = Popen(cmd)
    else:
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE)

    try:
        outs, errs = proc.communicate(timeout=timeout)
    except TimeoutExpired:
        is_timeout = True
        proc.kill()
        outs, errs = proc.communicate()

    return proc.returncode, is_timeout, outs, errs


def gen(aut, alphabet, csv_header, args=None):
    args = args or []
    workdir = mkdtemp(prefix="hnl", dir="/tmp")
    cmd = (
        [HNA_SCRIPT, "--out-dir", workdir, aut]
        + args
        + ["--csv-header", csv_header, "--alphabet", alphabet, "--build-type=Release"]
    )
    print(f"Generating monitor for '{aut}'")
    print(">", " ".join(cmd))

    ret = runcmd(cmd, no_capture=True)
    if ret[0] != 0:
        err(f"Generating monitor for {aut} failed")

    return workdir


def parse(retval, to, outs, errs):
    """
     -- verdict --
    HNA rejects
    -- stats --
    Number of HNL monitors: 2
    CPU time in milliseconds: 0.076709 ms

    """
    if retval < 0:
        print(outs)
        print(errs)

    if to:
        return "TO", "TO", "TO"

    verdict = None
    cputime = None
    for line in outs:
        if b"CPU time" in line:
            assert cputime is None
            cputime = float(line.split()[4])
        elif b"HNA " in line:
            assert verdict is None
            verdict = line.split()[1].strip()

    return retval, verdict.decode("ascii") if verdict else None, cputime


def measure(inputs, timeout=30):
    values = []
    for n in range(TRIALS):
        retval, is_timeout, outs, errs = runcmd([f"{mondir}/monitor"] + inputs)
        values.append(parse(retval, is_timeout, outs.splitlines(), errs.splitlines()))

    return values


# numbers on 3 bits
# alphabet=[str(i) for i in range(0, 2)]
# alphabet=[str(i) for i in range(0, 2**4)]
# alphabet=[str(i) for i in range(0, 2)]
# alphabet=[str(i) for i in range(0, 2**2)]
# alphabet=[str(i) for i in range(0, 2**3)]
# alphabet=[str(i) for i in range(0, 2**2)]
BITS = 4
alphabet = [str(i) for i in range(0, 2**BITS)]
csv_header = "loc: int, out: int"

if len(sys.argv) > 1:
    mondir = sys.argv[1]
else:
    mondir = gen("mot.yml", ",".join(alphabet), csv_header, args=["test.cpp"])

# chdir(mondir)
# r = runcmd(['make', 'check', '-j4'], no_capture=True)
# if r[0] != 0:
#     err("Failed tests")


def _run_measurement(NUM, LEN, method):
    if method == "rand-inputs":
        traces_dir = f"{mondir}/traces-{method}"
        ha_gen_traces_rand_inputs(alphabet, traces_dir, num=NUM, length=LEN)
    elif method == "almost-same":
        traces_dir = f"{mondir}/traces-{method}"
        ha_gen_traces_almost_same(alphabet, traces_dir, num=NUM, length=LEN)
    elif method == "same":
        traces_dir = f"{mondir}/traces-{method}"
        ha_gen_traces_same(alphabet, traces_dir, num=NUM, length=LEN)
    else:
        raise RuntimeError("Invalid config")

    inputs = [
        f"{abspath(pathjoin(traces_dir, f))}"
        for f in listdir(traces_dir)
        if f.endswith(".csv")
    ]

    verdict = None
    times = []
    for values in measure(inputs):
        W.writerow([method, NUM, LEN] + [values[1], values[2]])
        sys.stdout.flush()

        if values[0] < 0:
            print("Warning: a crash")

        # check that the verdict is stable
        if verdict:
            assert verdict == values[1] or values[0] < 0, (verdict, values)
        else:
            verdict = values[1]

        times.append(values[2])
    return times


with open(f"output-mot-{BITS}.csv", "a") as f:
    W = csv.writer(f)

    # for method in ("same", "almost-same", "rand-inputs"):
    # for method in ("almost-same", "rand-inputs"):
    for method in ("same",):
        print(f"--- Starting measurements for {method} ---")
        # for NUM in (100, 200, 300, 400, 500):
        #    for LEN in (500, 1000, 1500, 2000):
        for NUM in (50, 100, 200, 500):
            for LEN in (500, 1000, 2000):
                times = _run_measurement(NUM, LEN, method)
                times = [t for t in times if t]
                if times:
                    print(
                        f"Avg cputime {method}, {NUM}, {LEN}: {mean(times)*1e-3}s +- {stdev(times)*1e-3 if len(times) > 1 else None} ms"
                    )
                else:
                    print(f"Failed measuring times")


chdir("/tmp")
# rmtree(mondir)
