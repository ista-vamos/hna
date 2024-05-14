#ifndef MONITOR_H_
#define MONITOR_H_

#include <vector>
#include <list>
#include <memory>

#include "trace.h"
#include "traceset.h"
#include "verdict.h"
#include "monitor.h"

class SlicesTree {
    Monitor *root{nullptr};

    // map hnl monitors (they are nodes) to (action, hnlmonitor) pairs
    std::map<Monitor *, std::map<Action, Monitor *> _edges;
}

class HNAMonitor : public Monitor {

  std::vector<std::unique_ptr<Monitor>> _hnl_monitors;
  // Mapping of traces (their IDs) to HNL monitors they are currently in
  std::map<unsigned, Monitor *> _trace_to_monitor;
  SlicesTree _slices_tree;

  bool _traces_finished{false};

public:
 /*
  AtomMonitor *createAtomMonitor(Action monitor_type, HNLInstance&);
  void removeInstance(HNLInstance *instance);
  */

  // adding and extending traces
  void newTrace(unsigned id);
  void extendTrace(unsigned trace_id, const Event &e);
  void traceFinished(unsigned trace_id);
  void tracesFinished();

  Verdict step();

  // statistics
  struct {
    // number of HNL monitors
    size_t num_hnl_monitors{0};
  } stats;
};


#endif
