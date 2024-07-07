import argparse


def create_cmdargs_parser():
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
    return parser
