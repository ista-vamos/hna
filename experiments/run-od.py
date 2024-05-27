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

SRCDIR=f"{dirname(sys.argv[0])}/../"
HNL_SCRIPT=f"{SRCDIR}/hnl.py"
TRIALS=10 # how many times run the monitor on a given input

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

def gen(formula, alphabet, csv_header, args=None):
    args = args or []
    workdir = mkdtemp(prefix="hnl", dir="/tmp")
    cmd = [HNL_SCRIPT, '--out-dir', workdir, formula] +\
          args +\
          ['--csv-header', csv_header,
           '--alphabet', alphabet,
           "--build-type=Release"]
    print(f"Generating monitor for '{formula}'")
    print(">", " ".join(cmd))

    ret = runcmd(cmd, no_capture=True)
    if ret[0] != 0:
        err(f"Generating monitor for {formula} failed")

    return workdir

def parse(retval, to, outs, errs):
    """
     -- verdict --
    Formula is TRUE
    -- stats --
    Total formula instances: 1
    Total atom monitors: 2
    CPU time in milliseconds: 2.14529 ms
      from which:
      - generating instances took: 1.03733 ms
    """

    if to:
        return "TO", "TO", "TO"

    verdict = None
    cputime = None
    for line in outs:
        if b'CPU time' in line:
            assert cputime is None
            cputime = float(line.split()[4])
        elif b'Formula is' in line:
            assert verdict is None
            verdict = line.split()[2].strip()

    return retval, verdict, cputime


def measure(inputs, timeout=30):
    values = []
    for n in range(TRIALS):
        retval, is_timeout, outs, errs = runcmd([f'{mondir}/monitor'] + inputs)
        values.append(parse(retval, is_timeout, outs.splitlines(), errs.splitlines()))

    return values

def gen_traces_single_input(alphabet, outdir, num, length):
    """
    Generate traces that are OD. The input is in the first event
    and then stutters, if two traces share the same input,
    then one trace's outputs are a prefix of the other
    """
    makedirs(outdir, exist_ok=True)

    all_traces = []
    traces = {}
    alphabet=alphabet.split(",")
    for i in range(1, num + 1):
        a_i = alphabet[randrange(0, len(alphabet))]
        trace_in = []
        trace_out = []

        trace_in = [a_i] * length
        if str(trace_in) in traces:
            trace_out = traces[str(trace_in)]
        else:
            for n in range(length):
                a_o = alphabet[randrange(0, len(alphabet))]
                trace_out.append(a_o)
            traces[str(trace_in)] = trace_out
        all_traces.append((trace_in, trace_out))

    for n, t in enumerate(all_traces):
        with open(f"{outdir}/{n}.csv", "w") as f:
            f.write("in,out\n")
            for i in range(0, max(len(t[0]), len(t[1]))):
                i1 = i if i < len(t[0]) else len(t[0]) - 1
                i2 = i if i < len(t[1]) else len(t[1]) - 1
                f.write(f"{t[0][i1]}, {t[1][i2]}\n")


def gen_traces_two_inputs(alphabet, outdir, num, length):
    """
    Generate traces that are OD. The input is in the first event
    and then stutters, if two traces share the same input,
    then one trace's outputs are a prefix of the other
    """
    makedirs(outdir, exist_ok=True)

    all_traces = []
    traces = {}
    alphabet=alphabet.split(",")
    for i in range(1, num + 1):
        a_i1 = alphabet[randrange(0, len(alphabet))]
        a_i2 = alphabet[randrange(0, len(alphabet))]
        trace_in = []
        trace_out = []

        trace_in = [a_i1] + [a_i2] * (length - 1)
        if str(trace_in) in traces:
            trace_out = traces[str(trace_in)]
        else:
            for n in range(length):
                a_o = alphabet[randrange(0, len(alphabet))]
                trace_out.append(a_o)
            traces[str(trace_in)] = trace_out
        all_traces.append((trace_in, trace_out))

    for n, t in enumerate(all_traces):
        with open(f"{outdir}/{n}.csv", "w") as f:
            f.write("in,out\n")
            for i in range(0, max(len(t[0]), len(t[1]))):
                i1 = i if i < len(t[0]) else len(t[0]) - 1
                i2 = i if i < len(t[1]) else len(t[1]) - 1
                f.write(f"{t[0][i1]}, {t[1][i2]}\n")

def gen_traces_rand_inputs(alphabet, outdir, num, length):
    """
    Generate traces that are OD. The input is in the first event
    and then stutters, if two traces share the same input,
    then one trace's outputs are a prefix of the other
    """
    makedirs(outdir, exist_ok=True)

    all_traces = []
    traces = {}
    alphabet=alphabet.split(",")
    for i in range(1, num + 1):
        trace_in = []
        trace_out = []

        for n in range(length):
            a_i = alphabet[randrange(0, len(alphabet))]
            trace_in.append(a_i)

        if str(trace_in) in traces:
            trace_out = traces[str(trace_in)]
        else:
            for n in range(length):
                a_o = alphabet[randrange(0, len(alphabet))]
                trace_out.append(a_o)
            traces[str(trace_in)] = trace_out
        all_traces.append((trace_in, trace_out))

    for n, t in enumerate(all_traces):
        with open(f"{outdir}/{n}.csv", "w") as f:
            f.write("in,out\n")
            for i in range(0, max(len(t[0]), len(t[1]))):
                i1 = i if i < len(t[0]) else len(t[0]) - 1
                i2 = i if i < len(t[1]) else len(t[1]) - 1
                f.write(f"{t[0][i1]}, {t[1][i2]}\n")



# numbers on 3 bits
alphabet="0,1,2,3,4,5,6,7"
csv_header = "in: int, out: int"

if len(sys.argv) > 1:
    mondir = dirname(sys.argv[1])
else:
    mondir = gen("forall t1, t2: !(in(t1) <= in(t2)) || (out(t1) <= out(t2))",
                 alphabet, csv_header)

# chdir(mondir)
# r = runcmd(['make', 'check', '-j4'], no_capture=True)
# if r[0] != 0:
#     err("Failed tests")

def _run_measurement(NUM, LEN, method):
    if method == "single-input":
        traces_dir = f"{mondir}/traces-{method}"
        gen_traces_single_input(alphabet, traces_dir, num=NUM, length=LEN)
    elif method == "two-inputs":
        traces_dir = f"{mondir}/traces-{method}"
        gen_traces_two_inputs(alphabet, traces_dir, num=NUM, length=LEN)
    elif method == "rand-inputs":
        traces_dir = f"{mondir}/traces-{method}"
        gen_traces_two_inputs(alphabet, traces_dir, num=NUM, length=LEN)
    else:
        raise RuntimeError("Invalid config")

    inputs = [f"{abspath(pathjoin(traces_dir, f))}" for f in listdir(traces_dir) if f.endswith(".csv")]

    verdict = None
    times = []
    for values in measure(inputs):
        W.writerow([NUM, LEN] + [values[1], values[2]])
        sys.stdout.flush()

        # check that the verdict is stable
        if verdict:
            assert verdict == values[1], (verdict, values)
        else:
            verdict = values[1]

        times.append(values[2])
    return times

with open("output.csv", "a") as f:
    W = csv.writer(f)

    for method in ("single-input", "two-inputs", "rand-inputs"):
        print(f"--- Starting measurements for {method} ---")
        for NUM in (100, 200, 300, 400, 500):
            for LEN in (500, 1000, 1500, 2000):
                times = _run_measurement(NUM, LEN, method)
                print(f"Avg cputime {method}, {NUM}, {LEN}: {mean(times)*1e-3}s +- {stdev(times)*1e-3} ms")


chdir("/tmp")
rmtree(mondir)

