#ifndef MONITOR_H_
#define MONITOR_H_

#include <vector>
#include <list>
#include <memory>

#include "trace.h"
#include "traceset.h"
#include "verdict.h"
#include "atommonitor.h"

/* generated */
#include "hnlinstance.h"

///
// This is the interface for monitors. The methods are not virtual
// intentionally, the monitors will not be used through this class.
// The methods here just give the interface.
class Monitor {
public:
  /// adding a new trace to the monitor with ID `id`
  void newTrace(unsigned id);

  /// extend the trace with ID `trace_id` with the event `e`
  void extendTrace(unsigned trace_id, const Event &e);

  /// Notify the end of the trace
  void traceFinished(unsigned trace_id);

  /// Notify that no new trace can come in the future
  void tracesFinished(unsigned trace_id);
};


class HNLMonitor : public Monitor {
  TraceSet _traces;
  bool _traces_finished{false};

  std::vector<std::unique_ptr<HNLInstance>> _instances;
  std::list<std::unique_ptr<AtomMonitor>> _atom_monitors;

public:
  AtomMonitor *createAtomMonitor(Action monitor_type, HNLInstance&);
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


#endif
