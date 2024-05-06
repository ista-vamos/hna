#include "monitor.h"

Verdict HNLMonitor::step() {
  if (auto *trace = _traces.getNewTrace()) {
      _cfgs.emplace_back(trace);
  }

  for (auto &cfg : _cfgs) {
    auto *ev = cfg.trace->try_get(cfg.pos);
    if (ev) {
      std::cout << "MON: " << *ev << "\n";
      ++cfg.pos;
      if (cfg.finished()) {
        std::cout << "REMOVE CFG\n";
      }
    }
  }

  return Verdict::UNKNOWN;
}
