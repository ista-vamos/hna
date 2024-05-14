#ifndef MONITOR_H_
#define MONITOR_H_

#include <vector>
#include <list>
#include <memory>

#include "trace.h"
#include "traceset.h"
#include "verdict.h"
#include "monitor.h"
#include "atom-monitor.h"

/* generated */
#include "hnl-instance.h"

#include "namespace-start.h"

class HNLMonitor : public Monitor {
  TraceSet _traces;
  bool _traces_finished{false};

  std::vector<std::unique_ptr<HNLInstance>> _instances;
  std::list<std::unique_ptr<AtomMonitor>> _atom_monitors;

public:
  AtomMonitor *createAtomMonitor(HNLEvaluationState monitor_type, HNLInstance&);
  void removeInstance(HNLInstance *instance);

  // adding and extending traces
  void newTrace(unsigned id);
  void extendTrace(unsigned trace_id, const Event &e);
  void traceFinished(unsigned trace_id);
  void tracesFinished();

  Verdict step();

  // statistics
  struct {
    // number of HNL configurations
    size_t num_instances{0};
    // number of atom monitors
    size_t num_atoms{0};
  } stats;
};

#include "namespace-end.h"

#endif
