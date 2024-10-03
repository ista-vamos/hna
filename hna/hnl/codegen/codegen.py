from itertools import chain
from os import readlink
from os.path import abspath, dirname, islink, join as pathjoin, basename
from sys import stderr

from hna.codegen_common.codegen import CodeGen
from hna.codegen_common.utils import dump_codegen_position
from hna.hnl.formula import (
    Constant,
    Function,
    PrenexFormula,
)
from hna.hnl.codegen.submonitors.atoms import CodeGenCpp as CodeGenCppAtomsMon
from hna.hnl.codegen.submonitors.submon import CodeGenCpp as CodeGenCppSubMon


def _check_functions(functions):
    funs = {}
    for fun in functions:
        f = funs.get(fun.name)
        if f is None:
            funs[fun.name] = fun
        else:
            if len(f.traces) != len(fun.traces):
                raise RuntimeError(
                    f"Function '{fun.name}' is used multiple time with different number of arguments:\n{fun} and {f}"
                )


class CodeGenCpp(CodeGen):
    """
    Class for generating monitors in C++.
    The main function to be called is `generate`.

    This particular class takes care of creating `main.cpp` and files
    shared with all the (sub-)monitors.
    For actual monitors, there are other codegens.
    """

    def __init__(self, args, ctx, out_dir: str = None, namespace: str = None):
        super().__init__("monitor", args, ctx, out_dir, namespace)

        self_dir = abspath(
            dirname(readlink(__file__) if islink(__file__) else __file__)
        )
        self.templates_path = pathjoin(self_dir, "templates/")

        assert (
            self.args.csv_header
        ), "Give --csv-header, other methods not supported yet"
        self._event = [
            [s.strip() for s in event.split(":")]
            for event in self.args.csv_header.split(",")
        ]

    def copy_files(self):
        # copy files from the CMD line
        for f in self.args.cpp_files:
            self.copy_file(f)

        # copy common templates
        files = [
            "monitor.h",
            "cmd.h",
            "cmd.cpp",
            "stream.h",
            "trace.h",
            "trace.cpp",
            "tracesetbase.h",
            "tracesetbase.cpp",
            "traceset.h",
            "traceset.cpp",
            "tracesetview.h",
            "tracesetview.cpp",
            "sharedtraceset.h",
            "sharedtraceset.cpp",
            "verdict.h",
            # XXX: do this only when functions are used
            "function.h",
        ]

        from_dir = self.common_templates_path
        for f in files:
            if f not in self.args.overwrite_file:
                self.copy_file(f, from_dir=from_dir)

    def generate_cmake(self, overwrite_keys=None, embedding_data=None):
        """
        `embedded` is True if the HNL monitor is a subdirectory in some other project
        """
        from config import vamos_buffers_DIR

        build_type = self.args.build_type
        if not build_type:
            build_type = '"Debug"' if self.args.debug else "Release"

        if embedding_data is not None:
            raise NotImplementedError("HERE")

        values = {
            "@vamos-buffers_DIR@": vamos_buffers_DIR,
            "@additional_sources@": " ".join(
                (
                    basename(f)
                    for f in self.args.cpp_files
                    + self.args.add_gen_files
                    + self._add_gen_files
                )
            ),
            "@additional_cflags@": " ".join((d for d in self.args.cflags)),
            "@CMAKE_BUILD_TYPE@": build_type,
            "@monitor_name@": self.name(),
            "@submonitors_libs@": " ".join((d["name"] for d in self._submonitors)),
            "@submonitors@": "\n".join(
                (f'add_subdirectory({d["out_dir_rel"]})' for d in self._submonitors)
            ),
        }
        if overwrite_keys:
            values.update(overwrite_keys)

        if embedding_data is not None:
            cmakelists = "CMakeLists-top-embedded.txt.in"
        else:
            cmakelists = "CMakeLists-top.txt.in"
        self.gen_config(cmakelists, "CMakeLists.txt", values)

    def _generate_events(self):
        with self.new_file("events.h") as f:
            wr = f.write
            wr("#ifndef EVENTS_H_\n#define EVENTS_H_\n\n")
            wr("#include <iostream>\n")
            wr("#include <cstdint>\n\n")
            # wr("#include <cassert>\n\n")

            dump_codegen_position(wr)
            wr("struct Event {\n")
            for name, ty in self._event:
                wr(f"  {ty} {name};\n")
            wr("};\n\n")

            wr("std::ostream& operator<<(std::ostream& os, const Event& ev);\n")

            wr("#endif\n")

        with self.new_file("events.cpp") as f:
            wr = f.write
            wr("#include <iostream>\n\n")
            wr('#include "events.h"\n\n')
            dump_codegen_position(wr)
            wr("std::ostream& operator<<(std::ostream& os, const Event& ev) {\n")
            wr('  os << "("')
            for n, field in enumerate(self._event):
                name, ty = field
                if n > 0:
                    wr(f'  << ", "')
                wr(f'  << "{name} = " << ev.{name}')
            wr('   << ")";\n')
            wr("return os;\n")
            wr("}\n")

    def _generate_csv_reader(self):
        self.copy_file("csvreader.h", from_dir=self.common_templates_path)
        self.copy_file("csvreader.cpp", from_dir=self.common_templates_path)
        self._add_gen_files.append("csvreader.cpp")

        with self.new_file("csvreader-aux.h") as f:
            dump_codegen_position(f)

        with self.new_file("read_csv_event.h") as f:
            wr = f.write
            wr(f"int ch;\n\n")
            for n, tmp in enumerate(self._event):
                name, ty = tmp
                # wr(f"char action[{max_len_action_name}];\n\n")
                wr(f"_stream >> ev.{name};\n")
                wr("if (_stream.fail()) {")
                if n == 0:  # assume this is the header
                    wr(" if (_events_num_read == 0) {\n")
                    wr("   _stream.clear(); // assume this is the header\n")
                    wr("   // FIXME: check that the header matches the events \n")
                    wr("   // ignore the rest of the line and try with the next one\n")
                    wr(
                        "   _stream.ignore(std::numeric_limits<std::streamsize>::max(), '\\n');\n"
                    )
                    wr(f"   _stream >> ev.{name};\n")
                    wr("    if (_stream.fail()) {")
                    wr(
                        f'    std::cerr << "Failed reading column \'{name}\' on line " << _events_num_read + 1 << "\\n";'
                    )
                    wr("    abort();")
                    wr("  }")
                    wr("} else {")
                    wr(
                        f'    std::cerr << "Failed reading column \'{name}\' on line " << _events_num_read + 1 << "\\n";'
                    )
                    wr("    abort();")
                    wr("}")
                else:
                    wr(
                        f'  std::cerr << "Failed reading column \'{name}\' on line " << _events_num_read + 1 << "\\n";'
                    )
                    wr("  abort();")
                wr("}")
                if n == len(self._event) - 1:
                    wr(
                        f"""
                    while ((ch = _stream.get()) != EOF) {{
                      if (ch == '\\n') {{
                        break;
                      }}
                      
                      if (!std::isspace(ch)) {{
                        std::cerr << "Wrong input on line " << _events_num_read + 1 << " after reading column '{name}'\\n";
                        std::cerr << "Expected the end of line, got '" << static_cast<char>(ch) << "'\\n";
                        abort();
                      }}
                    }}
                    """
                    )
                else:
                    wr(
                        f"""
                    while ((ch = _stream.get()) != EOF) {{
                      if (ch == ',') {{
                        break;
                      }}
                      
                      if (!std::isspace(ch) || ch == '\\n') {{
                        std::cerr << "Wrong input on line " << _events_num_read + 1 << " after reading column '{name}'\\n";
                        std::cerr << "Expected next column (',' character), got '" << static_cast<char>(ch) << "'\\n";
                        abort();
                      }}
                    }}
                    """
                    )

    def _gen_function_files(self, fun: Function):
        with self.new_file(f"function-{fun.name}.h") as f:
            wr = f.write
            ns = self.namespace()
            wr(
                f"""
            #ifndef _FUNCTION_{fun.name}_H__{ns}
            #define _FUNCTION_{fun.name}_H__{ns}
            """
            )

            wr('#include "function.h"\n')
            wr('#include "sharedtraceset.h"\n\n')

            wr(f"class Function_{fun.name} : public Function{{\n")

            wr("public:\n")
            wr(" virtual SharedTraceSet& getTraceSet(")
            wr(", ".join((f"Trace *{tr.name}" for tr in fun.traces)))
            wr(") = 0;\n")
            wr("};\n")
            wr("#endif\n")

    def generate_functions(self, functions):
        with self.new_file("functions.h") as f:
            dump_codegen_position(f)
            wr = f.write
            wr(f"#ifndef HNL_FUNCTIONS__{self.name()}\n")
            wr(f"#define HNL_FUNCTIONS__{self.name()}\n")
            wr("#include <memory>\n")
            wr('#include "function.h"\n\n')
            for fun in functions:
                wr(f'#include "function-{fun.name}.h"\n')
            wr("\n\n")
            for fun in functions:
                wr(
                    f"std::unique_ptr<Function> createFunction_{fun.name}(CmdArgs *cmd);\n"
                )
            wr(f"#endif // !HNL_FUNCTIONS__{self.name()}\n")

        for fun in functions:
            self._gen_function_files(fun)

    def generate_alltracesets_class(self, functions):

        with self.new_file("alltracesets.h") as f:
            dump_codegen_position(f)
            wr = f.write
            wr(f"#ifndef HNL_ALLTRACESETS__{self.name()}\n")
            wr(f"#define HNL_ALLTRACESETS__{self.name()}\n\n")

            wr('#include "traceset.h"\n')
            for fun in functions:
                wr(f'#include "function-{fun.name}.h"\n')

            wr("\n")

            wr(
                "/* An object passed to monitors with references to traces and functions */\n"
            )
            wr("struct AllTraceSets {\n")
            wr(" TraceSet& traces;")
            for fun in functions:
                wr(f"  Function_{fun.name}& {fun.name};\n")
            wr("\n")
            fun_args = ",".join(
                (f"Function_{fun.name}& {fun.name}" for fun in functions)
            )
            fun_init = ",".join((f"{fun.name}({fun.name})" for fun in functions))
            wr(
                f"  AllTraceSets(TraceSet& traces{', ' if fun_args else ''}{fun_args}) : traces(traces) {',' if fun_init else ''} {fun_init} {{}}\n"
            )
            wr("};\n\n")

            wr(f"#endif // !HNL_ALLTRACESETS__{self.name()}\n")

    def generate(self, formula: PrenexFormula, alphabet=None):
        """
        The top-level function to generate code
        """

        self.args.alphabet = alphabet or self._get_alphabet(formula)

        self._generate_events()

        if self.args.gen_csv_reader:
            self._generate_csv_reader()

        functions_instances = formula.functions()
        functions = list(set(functions_instances))
        # check types of functions
        _check_functions(functions_instances)

        self.generate_functions(functions)
        self.generate_alltracesets_class(functions)

        has_quantifier_alternation = formula.has_quantifier_alternation()
        # Generate the actual monitors. If there is no quantifier alternation,
        # generate directly the monitor for the body of the formula.
        # Otherwise, generate a monitor that has sub-monitors for the sub-formulas
        # where the formula alternates.
        submon_name = self.sub_name()
        nested_out_dir_rel = "submonitor"
        nested_out_dir = f"{self.out_dir}/{nested_out_dir_rel}"
        nested_namespace = self.sub_namespace()
        self._submonitors = [
            {
                "name": submon_name,
                "out_dir": nested_out_dir,
                "out_dir_rel": nested_out_dir_rel,
                "namespace": nested_namespace,
            }
        ]

        if has_quantifier_alternation:
            codegen = CodeGenCppSubMon(
                submon_name,
                self.args,
                self.ctx,
                out_dir=nested_out_dir,
                namespace=nested_namespace,
            )
        else:
            codegen = CodeGenCppAtomsMon(
                submon_name,
                self.args,
                self.ctx,
                out_dir=nested_out_dir,
                namespace=nested_namespace,
            )

        # FIXME: do this more elegantly, this is more or less a hack
        self.args.out_dir_overwrite = False
        codegen.generate_embedded(formula)

        self.generate_monitor(formula)
        self.generate_main()

        self.copy_files()
        # cmake generation should go at the end so that
        # it knows all the generated files
        self.generate_cmake()

        self.format_generated_code()

    def _get_alphabet(self, formula):
        if not self.args.alphabet:
            print(
                "No alphabet given, using constants from the formula: ",
                formula.constants(),
                file=stderr,
            )
            alphabet = formula.constants()
        else:
            alphabet = [Constant(a) for a in self.args.alphabet]
        assert alphabet, "The alphabet is empty"
        return alphabet

    def _functions_mon_h_str(self, functions):
        init = ", ".join(
            (
                f"function_{fun.name}(createFunction_{fun.name}(_cmd))"
                for fun in functions
            )
        )
        init = f", {init}" if init else ""
        return (
            "\n".join(
                (f"std::unique_ptr<Function> function_{fun.name};" for fun in functions)
            ),
            init,
        )

    def _functions_mon_cpp_str(self, functions):
        step = "\n".join((f"function_{fun.name}->step();" for fun in functions))
        finished = [" // check if also the function traces generators finished"] + [
            f"finished &= function_{fun.name}->allTracesFinished();"
            for fun in functions
        ]
        return step, "\n".join(finished)

    def generate_monitor(self, formula):
        functions_instances = formula.functions()
        functions = list(set(functions_instances))

        funs, funs_init = self._functions_mon_h_str(functions)
        funs_step, funs_finished = self._functions_mon_cpp_str(functions)
        alltracesets_init = ",".join(
            chain(
                ("_traces",),
                (
                    f"*static_cast<Function_{fun.name}*>(function_{fun.name}.get())"
                    for fun in functions
                ),
            )
        )

        values = {
            "@monitor_name@": self.name(),
            "@namespace@": self.namespace(),
            "@namespace_start@": self.namespace_start(),
            "@namespace_end@": self.namespace_end(),
            "@functions@": funs,
            "@functions_init@": funs_init,
            "@functions_step@": funs_step,
            "@functions_finished@": funs_finished,
            "@alltracesets_init@": alltracesets_init,
        }

        self.gen_file("hnl-monitor.h.in", "hnl-monitor.h", values)
        self.gen_file("hnl-monitor.cpp.in", "hnl-monitor.cpp", values)

    def generate_main(self):
        self.gen_file(
            "main.cpp.in",
            "main.cpp",
            {
                "@namespace_using@": (
                    f"using namespace {self._namespace};" if self._namespace else ""
                ),
            },
        )
