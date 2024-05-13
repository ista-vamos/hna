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
      #include "createinstances.h"
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
              auto *instance = *it;

                // FIXME: generate the code that branches on instance->state and verdict
                // instead of having statically compiled BDD in the data segment.
                // (less reads from memory)
              auto action = BDD[instance->state][verdict == Verdict::TRUE ? 1 : 2 ];
              if (action == RESULT_FALSE) {
                  // The whole HNL formula evaluated to FALSE for the traces in `instance`.
                  return Verdict::FALSE;
              }

              if (action == RESULT_TRUE) {
                  // The whole HNL formula is satisfied for the traces in `instance`,
                  removeInstance(instance);
                  continue;
              }

              // switch to new atom monitor
              assert(action > 0 && "Invalid next atom");
              instance->state = action;
              instance->monitor = createAtomMonitor(action, *instance);
          }

          _atom_monitors.erase(atom_monitor_erase_it);
      }
  }

  if (auto *t1 = _traces.getNewTrace()) {
      /* GENERATED */
      #include "createinstances.h"
  }

  if (_instances.empty() && _traces_finished) {
      assert(_atom_monitors.empty());
      return Verdict::TRUE;
  }

  return Verdict::UNKNOWN;
}

AtomMonitor *HNLMonitor::createAtomMonitor(Action monitor_type, HNLInstance& instance) {
    assert(monitor_type > 0 && "Invalid monitor type");

    AtomMonitor *monitor;

    /* GENERATED */
    #include "createatommonitor.h"

    monitor->setUsedBy(instance);
    _atom_monitors.emplace_back(monitor);

    ++stats.num_atoms;

    return monitor;
}

void HNLMonitor::removeInstance(HNLInstance *instance) {
    // FIXME: make this efficient
    auto it = std::find_if(_instances.begin(), _instances.end(), [&instance](auto& ptr) { return ptr.get() == instance; });
    assert (it != _instances.end());
    // Each HNLInstance waits exactly for one monitor, so it is safe to just remove
    // it as this monitor has finished and no other monitor can have a
    // reference to the configuration.
    *it = std::move(_instances[_instances.size() - 1]);
    _instances.pop_back();
}

void HNLMonitor::newTrace(unsigned trace_id) {
    _traces.newTrace(trace_id);
}

void HNLMonitor::extendTrace(unsigned trace_id, const Event &e) {
    Trace *trace = _traces.get(trace_id);
    assert(trace && "Do not have such a trace");

    trace->append(e);
}

void HNLMonitor::traceFinished(unsigned trace_id) {
  Trace *trace = _traces.get(trace_id);
  assert(trace && "Do not have such a trace");
  trace->setFinished();
}

void HNLMonitor::tracesFinished() {
  _traces_finished = true;
}
