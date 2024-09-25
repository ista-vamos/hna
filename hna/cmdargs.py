import argparse
from os.path import basename, abspath


def create_cmdargs_parser(out_dir):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input files or formulas (formula string, .hnl or .vsrc files, additional C++ files",
    )
    parser.add_argument(
        "--out-dir",
        action="store",
        default=out_dir,
        help=f"Output directory (default: {out_dir})",
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Compile in debugging mode and produce debugging files",
    )
    parser.add_argument(
        "--debug-prints",
        action="store_true",
        help="--debug + print debugging messages to stderr",
    )
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
        "--overwrite-file",
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

    parser.add_argument(
        "--reduction",
        action="store",
        help="Comma-separated list of 'reflexive','symmetric'",
        default=None,
    )

    return parser


def process_args(args):

    if args.debug_prints:
        args.debug = True

    args.input_file = None
    args.cpp_files = []
    args.add_gen_files = []
    args.sources_def = None
    args.cmake_defs = args.D

    args.overwrite_file = [basename(f) for f in args.overwrite_file]
    if args.alphabet:
        if args.alphabet[-1] == "b" and args.alphabet[:-1].isnumeric():
            args.alphabet = [str(n) for n in range(0, 2 ** int(args.alphabet[:-1]))]
        else:
            args.alphabet = list(map(lambda s: s.strip(), args.alphabet.split(",")))
    if args.reduction:
        args.reduction = list(map(lambda s: s.strip(), args.reduction.split(",")))

    for fl in args.inputs:
        if (
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

    assert args.gen_csv_reader, "Not generating the reader is not implemented yet"

    return args
