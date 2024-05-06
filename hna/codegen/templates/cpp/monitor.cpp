#include <cassert>

#include "monitor.h"
#include "atommonitor.h"
#include "atoms.h"


/*
Verdict AtomMonitor::step() {

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
  abort();

  // _cfgs.clear(); // do not store configurations, we won't need them anymore
  return Verdict::UNKNOWN;
}
  */

/* generated part START */
#include "actions.h"
#include "bdd-structure.h"
/* generated part END */

Verdict HNLMonitor::step() {
  Verdict verdict;

  if (auto *t1 = _traces.getNewTrace()) {
      /* GENERATED */
      #include "createcfgs.h"
  }

  constexpr unsigned STEP_NUM = 1;

  for (auto& atom_monitor : _atom_monitors) {
    if ((verdict = atom_monitor->step(STEP_NUM)) != Verdict::UNKNOWN) {

        std::cerr << "CACHE THE RESULT\n";
        // _verdicts[atom_monitor->kind()][{atom_monitor->t1(), atom_monitor->t2()}] = verdict;

        for (auto it = atom_monitor->used_by_begin(),
                  et = atom_monitor->used_by_end(); it != et; ++it) {
            auto *hnlcfg = *it;

            auto action = BDD[hnlcfg->state][verdict == Verdict::TRUE ? 1 : 2 ];
            if (action == RESULT_FALSE) {
                return Verdict::FALSE;
            }

            if (action == RESULT_TRUE) {
               std::cerr << "REMOVE CONFIGURATION AND ATOM MONITOR\n";
               continue;
            }

            // switch to new atom monitor
            hnlcfg->state = action;
            hnlcfg->monitor = createAtomMonitor(action, *hnlcfg);
        }
    }
  }

  return Verdict::UNKNOWN;
}

AtomMonitor *HNLMonitor::createAtomMonitor(Action monitor_type, HNLCfg& hnlcfg) {
    assert(monitor_type > 0 && "Invalid monitor type");

    /* GENERATED */
    AtomMonitor *monitor;

    #include "createatommonitor.h"

    monitor->usedBy(hnlcfg);
}
