from re import match
import argparse
from os.path import basename, abspath
from sys import argv

from rvhyno.hnl.codegen.utils import c_type_info
from rvhyno.utils import msg


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
        "--build-system", action="store", default=None,
        help="Force build system for the CMake project (e.g., Ninja, Unix Makefiles, ...). "
             "If not set, Ninja is used if available. If not set and Ninja is not available, CMake's default on the "
             "system is used."
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
        "--log",
        action="append",
        default=['info', 'warn', 'err'],
        help="Set messages to log, can be used multiple times, default=[info,warn,err], possible=[info,warn,err,dbg]",
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
        "--data",
        action="store",
        help="A comma separated list of 'name:type' pairs where name is a valid C name and type is a valid C *integer* type. "
        "This list basically defines the type of the events expected on traces. "
        "The types can be refined with annotations saying the range of numbers, e.g.: `int [8b]` "
        "meaning int with at most 8-bit values, or `int [0..100]` for numbers between 0 and 100 (limits included)."
        "Information from this option is used also to generate the reader for CSV files.\n"
        "One more option is to use `aps: name1, name2, ...` which means 'atomic propositions' and translates to "
        "`name1: bool, name2: bool, ...`.",
    )

    parser.add_argument(
        "--data-fun",
        action="append",
        help="User-defined functions to transform data (in the form of a transducer). The argument is a path to a YAML file describing the transducer.",
    )

    parser.add_argument(
        "--alphabet",
        action="store",
        help="A comma separated list of symbols to use as alphabet. The symbols must be storable in the types of data specified by --data "
        "and will be compared for equality based on that types, not by string equality.",
    )

    parser.add_argument(
        "--logic",
        action="store",
        default="shl",
        help="Set the logic to use: ehl, shl (default).",
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
        "--gen-atom-tests",
        action="store_true",
        default=False,
        help="Generate tests for atoms.",
    )
    parser.add_argument(
        "--gen-experiments",
        action="store_true",
        default=True,
        help="Generate sample experiments setup.",
    )
    parser.add_argument(
        "--reduction",
        action="store",
        help="Comma-separated list of 'reflexive','symmetric','transitive'",
        default=None,
    )

    return parser


def parse_type(ty: str):
    ty = ty.strip()
    matched = match(r"(.+)\s*\[\s*(\d+b|-?\d+\.\.-?\d+)\s*\]", ty)
    if matched:
        c_type = matched[1].strip()
        num_range = None
        groups_num = len(matched.groups())
        if groups_num == 2:
            nums = matched[2].strip()
            if nums[-1] == "b":
                bits = int(nums[:-1])
                if bits > 64:
                    raise RuntimeError(
                        f"Was not able to parse data type: {ty}. The bitwidth {bits} is too big."
                    )
                if bits < 0:
                    raise RuntimeError(
                        f"Was not able to parse data type: {ty}. The bitwidth {bits} is negative."
                    )
                bw, signed = c_type_info(c_type)
                if bits > 8*bw:
                    raise RuntimeError(
                        f"Was not able to parse data type: {ty}. "
                        f"The bitwidth {bits} is bigger than the bitwidth of the data type `{c_type}`."
                    )
                num_range =  (-(1 << (bits - 1)), ((1 << (bits - 1)) - 1)) if signed else (0, (1 << bits) - 1)
            elif ".." in nums:
                # TODO: we need better input sanitization here
                a, b = nums.split("..")
                num_range = (int(a), int(b))
            else:
                raise NotImplementedError(f"Invalid size info for a field: `{ty}`")
        return c_type, num_range

    # this is just an incomplete check
    # TODO:: once c_type_info is (close to) complete, use that for checking
    types = ("int", "char", "short", "long", "float", "double", "bool",
             "uint64_t", "int64_t", "uint32_t", "int32_t")
    if ty not in types and ty not in ("unsigned",):
        if ty not in (f"{sign} {t}" for t in types for sign in ("signed", "unsigned")):
            msg('warn', f"I do not know this C type: '{ty}', but I proceed.")
    # this is a C type without range annotations
    return ty, None


def process_args(args):

    if args.debug_prints:
        args.debug = True

    args.input_file = None
    args.cpp_files = []
    args.add_gen_files = []
    args.sources_def = None
    args.cmake_defs = args.D

    if args.data:
        tmp_data = []  # we use list to preserve the order of elements because of the CSV files
        types = args.data.lstrip()
        if types.startswith('aps:'):
            # this is a list of atomic propositions (a list of boolean variables)
            for name in types[5:].split(","):
                tmp_data.append((name.strip(), ('bool', (0,1))))
        else:
            types = types.split(",")
            for name_type in types:
                name, ty = name_type.split(":")
                tmp_data.append((name.strip(), parse_type(ty)))

        args.data = tmp_data

    if args.reduction:
        args.reduction = list(map(lambda s: s.strip(), args.reduction.split(",")))

    for fl in args.inputs + args.overwrite_file:
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

    args.overwrite_file = [basename(f) for f in args.overwrite_file]
    assert args.gen_csv_reader, "Not generating the reader is not implemented yet"

    args.cmd = argv[:]

    return args
