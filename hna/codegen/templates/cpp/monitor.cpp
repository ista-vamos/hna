#include <cassert>

#include "monitor.h"

Verdict AtomMonitor::step() {
  if (auto *t1 = _traces.getNewTrace()) {
      for (const auto &t2 : _traces) {
         _cfgs.emplace_back(_initial_state, t1, t2.get());
         // TODO: symmetry reduction
         _cfgs.emplace_back(_initial_state, t2.get(), t1);
      }
  }

  for (auto &cfg : _cfgs) {
    auto *ev1 = cfg.t1->try_get(cfg.p1);
    auto *ev2 = cfg.t2->try_get(cfg.p2);
    if (ev1 && ev2) {
      assert(false && "Not implemented");
      abort();

      std::cout << "MON: " << *ev1 << ", " << *ev2 << "\n";
      ++cfg.p1;
      ++cfg.p2;
      if (cfg.finished()) {
        std::cout << "REMOVE CFG\n";
      }
    }
  }

  return Verdict::UNKNOWN;
}
