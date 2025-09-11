#!/usr/bin/env python3

import argparse
import os
import signal
from datetime import datetime, timedelta
from multiprocessing import Pool
from os import listdir, access, X_OK
from os.path import dirname, realpath, abspath, join, isfile
from shutil import rmtree
from subprocess import Popen, PIPE, DEVNULL, run as runcmd, TimeoutExpired
from sys import stderr
from tempfile import mkdtemp
import logging

SELF_DIR = dirname(realpath(__file__))
LOG_FILE = abspath(join(SELF_DIR, "experiments.log"))
MONITOR_EXE = abspath(join(f"{SELF_DIR}/..", "monitor"))

logger = logging.getLogger(__name__)


def benchmark(arg):
    """
    Benchmark the monitor with one combination of parameters.

    This function is called for every tuple of parameters returned by `parameters_combinations`.

    This function does the following things:
      - generate traces if required (no `--traces` is given and `--traces-num` and `--traces-len` are given).
        For generating the traces, the functions from `generate-traces.py` are used.
      - run the monitor `args.trials` times on the given traces and with the given parameters
    """
    traces_num, traces_len, args = arg

    if args.traces:
        traces_dir = args.traces
    else:  # generate traces
        assert traces_num is not None
        assert traces_len is not None
        traces_dir = mkdtemp(dir="/tmp/", prefix="traces-")

        log(
            f"[{datetime.now().time()}] generating {traces_num} traces of lenght {traces_len}"
        )

        from generate_traces import generate_traces

        generate_traces(traces_dir, traces_num, traces_len)

    results = []

    for _ in range(args.trials):
        results.append(run_monitor(arg, traces_dir))

    if not args.traces:
        try:
            rmtree(traces_dir)
        except Exception as e:
            log("Failed removing traces: ", str(e))
            rmtree(traces_dir, ignore_errors=True)

    return results


def run_monitor(arg, traces_dir):
    traces_num, trace_len, args = arg
    cmd = [
        "/bin/time",
        "-f",
        "%Uuser %Ssystem %eelapsed %PCPU (%Xavgtext+%Davgdata %Mmaxresident)k",
        MONITOR_EXE,
        traces_dir,
    ]
    p = Popen(cmd, stderr=PIPE, stdout=PIPE, preexec_fn=os.setsid)
    try:
        out, err = p.communicate(timeout=args.timeout)
    except TimeoutExpired:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        out, err = p.communicate(timeout=10)
    # the `time` command generates output to stderr
    assert err is not None, cmd

    data = {}
    if p.returncode in (0, 1):
        for line in out.splitlines():
            line = line.strip()
            if b"TRUE" in line:
                data["verdict"] = "TRUE"
            elif b"FALSE" in line:
                data["verdict"] = "FALSE"

        for line in err.splitlines():
            if b"elapsed" in line:
                parts = line.split()
                assert b"user" in parts[0]
                assert b"elapsed" in parts[2]
                assert b"maxresident" in parts[5]
                data["cpu_time"] = float(parts[0][:-4])
                data["wall_time"] = float(parts[2][:-7])
                data["mem"] = int(parts[5][:-13]) / 1024.0
    else:
        msg = "Failed command:\n" + " ".join(cmd)
        log(msg)
        log("-- stdout ---")
        log(out)
        log("-- stderr ---")
        log(err)
        fatal_error(msg)

    return (
        traces_dir,
        traces_num,
        trace_len,
        data["verdict"],
        data["cpu_time"],
        data["wall_time"],
        data["mem"],
        p.returncode,
    )


def parameters_combinations(args):
    """
    Yield the combination of parameters with which to run the monitor.
    As the last parameter, we expect to pass `args`.
    """
    for N in args.traces_nums:
        for L in args.traces_lens:
            yield N, L, args


def run(args):
    log(f"Using {args.j or 'automatic number of'} threads, output file is `{args.out}`")
    print(
        f"\033[1;34mRunning using {args.j or 'automatic number of'} workers, output file is {args.out}\n\033[0m",
        file=stderr,
    )
    print("Traces lengths: ", args.traces_lens)
    print("Traces numbers: ", args.traces_nums)
    print("Run each combination of parameters", args.trials, "times")

    verbose = args.verbose

    N = len(args.traces_nums) * len(args.traces_lens) * args.trials
    n = 0

    print_log(f"Altogether, {N} runs get executed")
    print("\n-------------------------------------")

    start_time = datetime.now()
    print_log(f"Starting at {start_time.time()}")
    print("-------------------------------------")

    with Pool(processes=args.j) as pool, open(args.out, "w") as out:
        for rows in pool.imap_unordered(benchmark, parameters_combinations(args)):
            for row in rows:
                print(*row, file=out)

                progress = 100 * (n / N)
                if verbose:
                    print_log(f"{progress: .2f}%: ", *row)
                else:
                    print(f"\r\033[32;1mDone: {progress: .2f}%\033[0m", end="")

                n += 1

    print_log("\nAll done!")
    end_time = datetime.now()
    print("-------------------------------------")
    print_log(f"Finished at {end_time.time()} (duration: {(end_time - start_time)})")
    print("-------------------------------------")
    print_log(f"Results stored into `{args.out}`")


def parse_cmd():
    parser = argparse.ArgumentParser()
    parser.add_argument("-j", metavar="PROC_NUM", action="store", type=int)
    parser.add_argument(
        "--out",
        help="Name of the output file. Default is 'out.csv'",
        action="store",
        default="out.csv",
    )
    parser.add_argument(
        "--verbose",
        help="Print some extra messages",
        action="store_true",
        default=False,
    )
    # FIXME: allow multiple directories
    parser.add_argument(
        "--traces",
        metavar="DIR",
        help="Take traces from <DIR>. If this argument is not specified, random traces are generated "
        "using the values given by `--traces-lens` and `--traces-nums`.",
        action="store",
    )
    parser.add_argument(
        "--traces-lens",
        help="Comma-separated list of lenghts of traces",
        action="store",
        default="10",
    )
    parser.add_argument(
        "--traces-nums",
        help="Comma-separated list of numbers of traces",
        action="store",
        default="10",
    )
    parser.add_argument(
        "--trials",
        help="How many times repeat each run",
        action="store",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--timeout", help="In seconds", action="store", type=int, default=120
    )
    parser.add_argument(
        "--one-trace",
        help="Take one trace and pass it to the monitor `--traces-nums` times. "
        "If `--traces` is given, the first trace in the directory (lexicographically) is used.",
        action="store_true",
        default=False,
    )

    args = parser.parse_args()

    if isinstance(args.traces_lens, str):
        args.traces_lens = list(map(int, args.traces_lens.split(",")))
    if isinstance(args.traces_nums, str):
        args.traces_nums = list(map(int, args.traces_nums.split(",")))

    return args


def log(msg, *args, **kwargs):
    for a in args:
        logger.info(a)


def print_log(msg, *args, **kwargs):
    log(msg, *args, **kwargs)
    print(msg, *args, **kwargs)


def fatal_error(msg, *args, **kwargs):
    logging.error("==== ERROR ==== ")
    logging.error(msg)

    print("\033[31;1m==== ERROR ==== \033[0m", file=stderr)
    print(msg, file=stderr)
    print(f"Log written into `{LOG_FILE}`", file=stderr)

    raise RuntimeError("Fatal error")


if __name__ == "__main__":
    logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG)

    args = parse_cmd()
    log(str(args))

    if not (isfile(MONITOR_EXE) and access(MONITOR_EXE, X_OK)):
        fatal_error(f"Did not find the monitor, expected: `{MONITOR_EXE}`.")

    run(args)

    logging.shutdown()
