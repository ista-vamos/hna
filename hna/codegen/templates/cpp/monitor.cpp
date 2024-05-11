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

  for (auto atom_monitor_it = _atom_monitors.begin(),
            atom_monitor_et = _atom_monitors.end();
            atom_monitor_it != atom_monitor_et;) {
      auto *atom_monitor = atom_monitor_it->get();
      auto atom_monitor_erase_it = atom_monitor_it++;

      if ((verdict = do_step(atom_monitor)) != Verdict::UNKNOWN) {
          // std::cerr << "CACHE THE RESULT\n";
          // _verdicts[atom_monitor->kind()][{atom_monitor->t1(), atom_monitor->t2()}] = verdict;

          for (auto it = atom_monitor->used_by_begin(),
                    et = atom_monitor->used_by_end(); it != et; ++it) {
              auto *hnlcfg = *it;

                // FIXME: generate the code that branches on hnlcfg->state and verdict
                // instead of having statically compiled BDD in the data segment.
                // (less reads from memory)
              auto action = BDD[hnlcfg->state][verdict == Verdict::TRUE ? 1 : 2 ];
              if (action == RESULT_FALSE) {
                  std::cerr << "Atom evaluated to FALSE\n";
                  // The whole HNL formula evaluated to FALSE for the traces in `hnlcfg`.
                  return Verdict::FALSE;
              }

              if (action == RESULT_TRUE) {
                  std::cerr << "Atom evaluated to TRUE\n";
                  // The whole HNL formula is satisfied for the traces in `hnlcfg`,
                  removeCfg(hnlcfg);
                  continue;
              }

              // switch to new atom monitor
              assert(action > 0 && "Invalid next atom");
              hnlcfg->state = action;
              hnlcfg->monitor = createAtomMonitor(action, *hnlcfg);
          }

          _atom_monitors.erase(atom_monitor_erase_it);
      }
  }

  if (auto *t1 = _traces.getNewTrace()) {
      /* GENERATED */
      #include "createcfgs.h"
  }

  if (_cfgs.empty() && _traces.finished()) {
      assert(_atom_monitors.empty());
      return Verdict::TRUE;
  }

  return Verdict::UNKNOWN;
}

AtomMonitor *HNLMonitor::createAtomMonitor(Action monitor_type, HNLInstance& hnlcfg) {
    assert(monitor_type > 0 && "Invalid monitor type");

    AtomMonitor *monitor;

    /* GENERATED */
    #include "createatommonitor.h"

    monitor->setUsedBy(hnlcfg);
    _atom_monitors.emplace_back(monitor);

    ++stats.gen_atoms;

    return monitor;
}

void HNLMonitor::removeCfg(HNLInstance *cfg) {
    // FIXME: make this efficient
    auto it = std::find_if(_cfgs.begin(), _cfgs.end(), [&cfg](auto& ptr) { return ptr.get() == cfg; });
    assert (it != _cfgs.end());
    // Each HNLInstance waits exactly for one monitor, so it is safe to just remove
    // it as this monitor has finished and no other monitor can have a
    // reference to the configuration.
    *it = std::move(_cfgs[_cfgs.size() - 1]);
    _cfgs.pop_back();
}

