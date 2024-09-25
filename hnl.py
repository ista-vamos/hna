#!/usr/bin/env python3

import sys
from multiprocessing import cpu_count
from os.path import abspath, isfile, basename
from subprocess import run

from config import vamos_common_PYTHONPATH
from hna.cmdargs import create_cmdargs_parser, process_args
from hna.hnl.parser import Parser

sys.path.append(vamos_common_PYTHONPATH)

from hna.hnl.codegen import CodeGenCpp

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
    parser = create_cmdargs_parser()
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

    print(args)

    return args


if __name__ == "__main__":
    args = parse_arguments()
    main(args)
