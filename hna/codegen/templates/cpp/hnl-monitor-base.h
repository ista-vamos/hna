#ifndef HNLMONITOR_BASE_H_
#define HNLMONITOR_BASE_H_

#include <atomic>

#include "monitor.h"
#include "traceset.h"

template <typename TraceSetTy> class HNLMonitorBase : public Monitor {
protected:
  std::atomic<bool> _traces_finished{false};
  TraceSetTy _traces;

public:
  // adding and extending traces
  void newTrace(unsigned trace_id) { _traces.newTrace(trace_id); }

  void extendTrace(unsigned trace_id, const Event &e) {
    _traces.extendTrace(trace_id, e);
  }

  void traceFinished(unsigned trace_id) { _traces.traceFinished(trace_id); }

  void noFutureUpdates() {
    _traces_finished.store(true, std::memory_order_release);
  }

  bool allTracesFinished() { return _traces.allTracesFinished(); }

  bool hasTrace(unsigned trace_id) { return _traces.hasTrace(trace_id); }
};

#endif // HNLMONITOR_BASE_H_
