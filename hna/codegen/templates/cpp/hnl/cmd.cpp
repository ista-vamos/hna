#include <iostream>
#include <cstring>
#include <cassert>
#include "cmd.h"

bool CmdArgs::parse() {
  // the object should not be initialized
  assert(!trace_are_events);
  assert(!trace_is_signal);
  assert(!trace_are_aps);
  assert(inputs.empty());

  for (int i = 1; i < argc; ++i) {
    if (strcmp(argv[i], "--csv") == 0) {
      csv_reader = true;
    } else if (strcmp(argv[i], "--signal") == 0) {
      trace_is_signal = true;
    } else if (strcmp(argv[i], "--aps") == 0) {
      trace_are_aps = true;
    } else if (strcmp(argv[i], "--no-ignore-unknown") == 0) {
      ignore_unknown = false;
    } else if (argv[i][0] == '-') {
      std::cerr << "Invalid option: " << argv[i] << "\n";
      return false;
    } else {
      inputs.push_back(argv[i]);
    }
  }

  // the trace can be represented as a sequence of abstract events
  // or as a sequence of sets of atomic propositions
  if (!trace_are_aps) {
    trace_are_events = true;
  }

  return true;
}

void CmdArgs::help() const {
  std::cerr << "Usage: monitor [--no-ignore-unknown] [--csv] [--signal] [--aps]\n\n"
            << "  --no-ignore-unknown     Do not ignore unknown variables and constants in input.\n"
            << "  --csv                   Input files are CSV files.\n\n"
            << "If the monitor was generated with fixed input channels, it will use that\n"
            << "unless --csv is specified, in which case it is going to read traces from provided\n"
            << "CSV files. CSV is also the default option if the monitor had no input method specified.\n"
            << "With --csv, these additional options can be used:\n\n"
            << "  --aps     Lines in input file represent atomic propositions.\n"
            << "            If this option is missing, trace is considered to be a sequence of variable assignments.\n"
            << "  --signal  Lines specify changes in the state (signal semantics).\n";
}
