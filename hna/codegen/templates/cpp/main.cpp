#include <cassert>
#include <cstdlib>
#include <iostream>
#include <thread>

//#include "inputs.h"
#include "cmd.h"
#include "traceset.h"
#include "csvreader.h"

struct Cfg {
  Trace *trace;
  size_t pos{0};

  Cfg(Trace *t) : trace(t) {}

  bool finished() const {
    return trace->finished() && pos == trace->size();
  }
};

int monitor(TraceSet& traces) {
  std::cerr << "Entering monitor\n";
  std::vector<Cfg> cfgs;
  while (true) {
    if (auto *trace = traces.getNewTrace()) {
        cfgs.emplace_back(trace);
    }

    for (auto &cfg : cfgs) {
      auto *ev = cfg.trace->try_get(cfg.pos);
      if (ev) {
        std::cout << "MON: " << *ev << "\n";
        ++cfg.pos;
        if (cfg.finished()) {
          std::cout << "REMOVE CFG\n";
        }
      }
    }
  }
  return 0;
}

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
      inputs_thrd = std::thread([&cmd, &traceSet] {
                      read_csv<CSVEventsStream>(cmd, traceSet);
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

  auto ret = monitor(traceSet);
  inputs_thrd.join();

  return ret;
}
