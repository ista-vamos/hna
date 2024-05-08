#include <cassert>

#include "monitor.h"
#include "atommonitor.h"
#include "atoms.h"



/* generated part START */
#include "actions.h"
#include "bdd-structure.h"
/* generated part END */

static inline Verdict do_step(AtomMonitor *M) {
  #include "do_step.h"
}

Verdict HNLMonitor::step() {
  Verdict verdict;

  if (auto *t1 = _traces.getNewTrace()) {
      /* GENERATED */
      #include "createcfgs.h"
  }

  constexpr unsigned STEP_NUM = 1;

  for (auto& atom_monitor : _atom_monitors) {
    if ((verdict = do_step(atom_monitor.get())) != Verdict::UNKNOWN) {

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
               abort();
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

    AtomMonitor *monitor;

    /* GENERATED */
    #include "createatommonitor.h"

    monitor->setUsedBy(hnlcfg);
    _atom_monitors.emplace_back(monitor);

    return monitor;
}
