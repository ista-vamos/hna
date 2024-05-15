#ifndef HNLMONITOR_BASE_H_
#define HNLMONITOR_BASE_H_

#include "monitor.h"
#include "traceset.h"

class HNLMonitorBase : public Monitor {
protected:
  std::atomic<bool> _traces_finished{false};
  TraceSet _traces;

public:
  // adding and extending traces
  void newTrace(unsigned id);
  void extendTrace(unsigned trace_id, const Event &e);
  void traceFinished(unsigned trace_id);
  void noFutureUpdates();

  bool allTracesFinished();
  bool hasTrace(unsigned trace_id);

  // statistics
  struct {
    // number of HNL configurations
    size_t num_instances{0};
    // number of atom monitors
    size_t num_atoms{0};
  } stats;
};


#endif // HNLMONITOR_BASE_H_
