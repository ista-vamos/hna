#include <cassert>
#include <cstdlib>
#include <iostream>
#include <thread>

//#include "inputs.h"


class TraceSet {

};

class CmdArgs {
  int argc;
  char **argv;


int monitor(TraceSet& traces);

public:
  CmdArgs(int argc, char *argv[])
  : argc(argc), argv(argv) {}

  bool csv_reader{false};
  bool trace_are_events{false};
  bool trace_are_aps{false};
  bool trace_is_signal{false};

  bool parse();
};

void read_events_csv(CmdArgs& args, TraceSet& traces) {

}

int main(int argc, char *argv[]) {
  CmdArgs cmd(argc, argv);

  if (!cmd.parse()) {
    std::cerr << "Failed parsing command-line arguments.";
    return -1;
  }

  TraceSet traceSet{};
  std::thread inputs_thrd;

  if (cmd.csv_reader) {
    if (cmd.trace_are_events) {
      inputs_thrd = std::thread([&cmd, &traceSet]{read_events_csv(cmd, traceSet);});
    }

    assert(false && "Not implemented yet");
    abort();
    /*
    if (cmd.trace_are_aps)
    if (cmd.trace_is_signal)
    */
  }

  auto ret = monitor(traceSet);
  inputs_thrd.join();

  return ret;
}
