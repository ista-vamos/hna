#ifndef CMDARGS_H_
#define CMDARGS_H_

#include <string>
#include <vector>

/***
 * Class to parse command-line arguments
 */
class CmdArgs {
  int argc;
  char **argv;

public:
  CmdArgs(int argc, char *argv[]) : argc(argc), argv(argv) {}

  bool csv_reader{true};
  bool trace_are_events{false};
  bool trace_are_aps{false};
  bool trace_is_signal{false};
  // ignore unknown events and constants
  bool ignore_unknown{false};

  std::vector<std::string> inputs;

  // do not have open more than this amount of traces at once
  size_t open_traces_limit = 5000;
  // read at most this number of events before switching to extending some other
  // trace
  size_t read_max_num_events_at_once = 1000000;

  bool parse();
  void help() const;
};

#endif
