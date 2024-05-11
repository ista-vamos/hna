#include <cassert>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <cassert>

//#include "inputs.h"
#include "cmd.h"
#include "traceset.h"
#include "csvreader.h"
#include "monitor.h"


int main(int argc, char *argv[]) {
  CmdArgs cmd(argc, argv);

  if (!cmd.parse()) {
    std::cerr << "\033[0;31mFailed parsing command-line arguments.\033[0m\n\n";
    cmd.help();
    return -1;
  }

  TraceSet traceSet{};
  std::thread inputs_thrd;
  // set this to false to stop the inputs thread
  bool running = true;

  if (cmd.csv_reader) {
    if (cmd.trace_are_events) {
      inputs_thrd = std::thread([&cmd, &traceSet, &running] {
                      read_csv<CSVEventsStream>(cmd, traceSet, running);
                    });
    } else {
      assert(false && "Not implemented yet");
      abort();
    /*
    if (cmd.trace_are_aps)
    if (cmd.trace_is_signal)
    */
    }
  } else {
    assert(false && "Not implemeted yet");
  }

  HNLMonitor monitor(traceSet);

  Verdict verdict;
  do {
    verdict = monitor.step();
  } while (verdict == Verdict::UNKNOWN);

  // stop getting traces if there are events still coming
  running = false;

  inputs_thrd.join();

  assert(verdict != Verdict::UNKNOWN);
  std::cout << " -- verdict --\n";
  if (verdict == Verdict::TRUE)
      std::cout << "Formula is TRUE\n";
  else if (verdict == Verdict::FALSE)
      std::cout << "Formula is FALSE\n";
  std::cout << " -- stats --\n";
  std::cout << "  Total formula instances: " << monitor.stats.num_instances << "\n";
  std::cout << "  Total atom monitors: " << monitor.stats.num_atoms << "\n";

  return static_cast<int>(verdict);
}
