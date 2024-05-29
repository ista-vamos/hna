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

def gen_traces_single_input(alphabet, outdir, num, length):
    """
    Generate traces that are OD. The input is in the first event
    and then stutters, if two traces share the same input,
    then one trace's outputs are a prefix of the other
    """
    makedirs(outdir, exist_ok=True)

    all_traces = []
    traces = {}
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


