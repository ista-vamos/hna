#include <cassert>
#include <cstdlib>
#include <iostream>
#include <thread>

//#include "inputs.h"
#include "cmd.h"


class TraceSet {

};



void read_events_csv(CmdArgs& args, TraceSet& traces) {

}

int monitor(TraceSet& traces);

int main(int argc, char *argv[]) {
  CmdArgs cmd(argc, argv);

  if (!cmd.parse()) {
    std::cerr << "\033[0;31mFailed parsing command-line arguments.\033[0m\n\n";
    cmd.help();
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
