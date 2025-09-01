#!/usr/bin/env python3

import sys
from multiprocessing import cpu_count
from os.path import isfile, basename
from subprocess import run

# from config import vamos_common_PYTHONPATH
from rvhyno.cmdargs import create_cmdargs_parser, process_args
from rvhyno.hnl.parser import Parser
from rvhyno.utils import msg, open_log, log

# sys.path.append(vamos_common_PYTHONPATH)

from rvhyno.hnl.codegen import CodeGenCpp

script_name = basename(sys.argv[0])


def compile_monitor(args):
    build_system = args.build_system
    build_system_args = []
    if build_system is not None:
        build_system_args = ["-G", build_system]
    else:
        from shutil import which

        has_ninja = which("ninja") is not None
        if has_ninja:
            args.build_system = "Ninja"
            build_system_args = [
                "-G",
                "Ninja",
                "-DCMAKE_CXX_FLAGS=-fdiagnostics-color=always",
            ]

    run(
        ["cmake", "."] + build_system_args + [f"-D{x}" for x in args.cmake_defs],
        cwd=args.out_dir,
    )
    run(["cmake", "--build", ".", f"-j{int(2*cpu_count()) + 2}"], cwd=args.out_dir)


def main(args):
    ctx = None

    ### Parse formula
    msg("info", "Parsing formula", section=2)
    parser = Parser(ctx)
    formula = args.input_formula
    if isfile(formula):
        formula = parser.parse_path(formula)
    else:
        formula = parser.parse_text(formula)

    msg(None, "Formula: ", f"`{formula}`")
    log("dbg", "Formula simplified: ", f"`{formula.simplify()}`")
    log("dbg", "Quantifiers: ", f"`{[str(q) for q in formula.quantifiers()]}`")
    if not formula.is_hltl():
        log(
            "dbg",
            "Trace variables: ",
            f"`{[str(t) for t in formula.trace_variables()]}`",
        )
        log(
            "dbg",
            "Program variables: ",
            f"`{[str(p) for p in formula.program_variables()]}`",
        )
        log("dbg", "Constants: ", f"`{[str(c) for c in formula.constants()]}`")
        log("dbg", "Functions: ", f"`{formula.functions()}`")

        problems = formula.problems()
        if args.logic == "ehl" and not formula.is_simple():
            problems.append("Formula is not simple, eHL monitors require that")
        for problem in problems:
            msg("err", problem)
        if problems:
            raise RuntimeError("Ran into problems, bailing out...")

    msg("info", "Generating monitor code", section=2)
    codegen = CodeGenCpp(args, ctx)
    codegen.generate(formula)

    msg("info", f"Monitor generated into '{args.out_dir}'")
    if not args.gen_only:
        msg("info", "Compiling the monitor (can be suppressed by --gen-only)")
        compile_monitor(args)


def parse_arguments():
    parser = create_cmdargs_parser("/tmp/hnl")
    args = process_args(parser.parse_args())

    args.input_formula = None
    for fl in args.inputs:
        if not isfile(fl):
            if args.input_formula:
                raise RuntimeError(
                    f"Multiple formulas given (previous: {args.input_formula}, now: {fl})"
                )
            args.input_formula = fl
            continue

    if args.input_formula is None:
        raise RuntimeError("ERROR: Got no input formula.")

    if args.data is None:
        raise RuntimeError("ERROR: need --data parameter")

    log("dbg", args)

    return args


if __name__ == "__main__":
    with open_log("/tmp/hnl-log.md"):
        msg("info", f"Parsing arguments", section=2, log_only=True)
        args = parse_arguments()
        main(args)
