#!/usr/bin/env python3

import argparse
import sys
from multiprocessing import cpu_count
from os.path import abspath, isfile, basename
from subprocess import run

from config import vamos_common_PYTHONPATH
from hna.hnl.parser import Parser

sys.path.append(vamos_common_PYTHONPATH)

from hna.codegen.hnl import CodeGenCpp

# from vamos_mpt.parser import Parser

script_name = basename(sys.argv[0])


def msg(m):
    print(f"\033[0;34m[{script_name}]: {m}\033[0m", file=sys.stdout)


def dbg(m):
    print(f"\033[0;35m[{script_name}] DBG: {m}\033[0m", file=sys.stderr)


def compile_monitor(args):
    run(["cmake", "."] + [f"-D{x}" for x in args.cmake_defs], cwd=args.out_dir)
    run(["make", f"-j{int(cpu_count()/2)+1}"], cwd=args.out_dir)


def main(args):
    ctx = None

    ### Parse the event source specification if given and generate the sources
    # if args.sources_def:
    #    msg("generating event sources")
    #    from config import vamos_sources_PYTHONPATH
    #    sys.path.append(vamos_sources_PYTHONPATH)
    #    from vamos_sources.spec.parser.parser import InlineSpecParser as SrcParser
    #    from vamos_sources.codegen.cpp.codegen import CodeGenCpp as SrcCodeGenCpp

    #    src_parser = SrcParser()
    #    src_ast, ctx = src_parser.parse_path(args.sources_def)
    #    src_args = copy(args)
    #    src_codegen = SrcCodeGenCpp(src_args, ctx)
    #    src_codegen.generate(src_ast)
    #    msg("event sources generated")
    #    msg(f"ctx: {ctx}")
    #    ctx.dump()

    ### Parse formula
    msg("Generating monitor code")
    parser = Parser(ctx)
    formula = args.input_formula
    if isfile(formula):
        formula = parser.parse_path(formula)
    else:
        formula = parser.parse_text(formula)

    print("Formula: ", formula)
    print("Simplified:", formula.simplify())
    print("Removed stutter-red:", formula.remove_stutter_reductions())
    print("Formula again: ", formula)
    print("-----")
    print("Quantifiers: ", [str(q) for q in formula.quantifiers()])
    print("Trace variables: ", [str(t) for t in formula.trace_variables()])
    print("Program variables: ", [str(p) for p in formula.program_variables()])
    constants = formula.constants()
    print("Constants: ", [str(c) for c in constants])

    problems = formula.problems()
    if not formula.is_simple():
        problems.append("Formula is not simple, we require that for now")
    for problem in problems:
        print("\033[1;31m", problem, "\033[0m")
    if problems:
        exit(1)

    # if args.sources_def:
    #    # these files were generated by the source codegen
    #   #args.add_gen_files.append("src.cpp")
    #   #args.add_gen_files.append("inputs.cpp")
    #    # do not overwrite what the source codegen generated
    #    args.out_dir_overwrite = False

    codegen = CodeGenCpp(args, ctx)
    codegen.generate(formula)

    # msg("generating events")
    # assert args.out_dir_overwrite is False
    # events_codegen = EventsCodeGen(args, ctx)
    # events_codegen.generate(mpt.alphabet)
    # msg("DONE generating events")

    # msg("generating traces classes")
    # assert args.out_dir_overwrite is False
    # traces_codegen = TracesCodeGen(args, ctx)
    # traces_codegen.generate(ctx.tracetypes, mpt.alphabet)
    # msg("DONE generating traces")

    # mpt.todot()
    # print(ast.pretty())
    msg(f"Monitor generated into '{args.out_dir}'")
    if not args.gen_only:
        msg("-- Compiling the monitor --")
        compile_monitor(args)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input files or formulas (formula string, .hnl or .vsrc files, additional C++ files",
    )
    parser.add_argument(
        "--out-dir",
        action="store",
        default="/tmp/hnl",
        help="Output directory (default: /tmp/hnl)",
    )
    parser.add_argument(
        "--out-dir-overwrite",
        action="store",
        default=True,
        help="Overwrite the contents of the output dir if it exists (default: True)",
    )
    parser.add_argument(
        "--build-type", action="store", help="Force build _type for the CMake project"
    )
    parser.add_argument(
        "--sanitize", action="store", help="Compile the monitor with sanitizers"
    )
    parser.add_argument("--debug", action="store_true", help="Debugging mode")
    parser.add_argument(
        "--exit-on-error", action="store_true", help="Stop when a violation is found"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print more messages"
    )
    parser.add_argument("--stats", action="store_true", help="Gather statistics")
    parser.add_argument(
        "-D", action="append", default=[], help="Additional CMake definitions"
    )
    parser.add_argument(
        "--cflags",
        action="append",
        default=[],
        help="Additional C flags for the compiler",
    )
    parser.add_argument(
        "--alphabet",
        action="store",
        help="Comma-separated list of letter to use as the alphabet",
    )
    parser.add_argument(
        "--overwrite-default",
        action="append",
        default=[],
        help="Do not generate the default version of the given file, its replacement is assumed to be "
        "provided as an additional source.",
    )
    parser.add_argument(
        "--gen-only",
        action="store_true",
        default=False,
        help="Do not try to compile the project, just generate the sources",
    )
    parser.add_argument(
        "--gen-csv-reader",
        action="store_true",
        default=True,
        help="Generate code that can read CSV files as input. "
        "It is enabled by default even for monitors with other "
        "inputs (for testing). See --help of the monitor binary "
        "for instructions on how to use the CSV reader if the monitor has also other inputs.",
    )
    parser.add_argument(
        "--csv-header",
        action="store",
        help="The header for CSV with types, a comma separated list of 'name:type' pairs where name is a valid C name and type is a valid C type",
    )
    args = parser.parse_args()

    args.input_formula = None
    args.cpp_files = []
    args.add_gen_files = []
    args.sources_def = None
    args.cmake_defs = args.D
    for fl in args.inputs:
        if not isfile(fl):
            if args.input_formula:
                raise RuntimeError(
                    f"Multiple formulas given (previous: {args.input_formula}"
                )
            args.input_formula = fl
            continue

        if fl.endswith(".mpt"):
            if args.input_formula:
                raise RuntimeError("Multiple .mpt files given")
            args.input_formula = fl
        elif (
            fl.endswith(".cpp")
            or fl.endswith(".h")
            or fl.endswith(".hpp")
            or fl.endswith(".cxx")
            or fl.endswith("cc")
        ):
            args.cpp_files.append(abspath(fl))
        elif fl.endswith(".vsrc"):
            if args.sources_def:
                raise RuntimeError("Multiple .vsrc files given")
            args.sources_def = fl

    if args.alphabet:
        args.alphabet = list(map(lambda s: s.strip(), args.alphabet.split(",")))

    print(args)

    assert args.gen_csv_reader, "Not generating the reader is not implemented yet"

    return args


if __name__ == "__main__":
    args = parse_arguments()
    main(args)
