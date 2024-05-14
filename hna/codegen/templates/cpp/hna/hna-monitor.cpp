#include <cassert>

#include "hna-monitor.h"

Verdict HNLMonitor::step() {
  Verdict verdict;


  return Verdict::UNKNOWN;
}

void HNAMonitor::newTrace(unsigned trace_id) {
    assert(_trace_to_monitor.count(trace_id) == 0);

    root_monitor->newTrace(trace_id);
    _trace_to_monitor[trace_id] = root_monitor;
}

void HNAMonitor::extendTrace(unsigned trace_id, const Event &e) {
    if (e.isAction()) {
        abort();
    } else {
        auto *M = getSlice(trace_id);
        assert(M && "Do not have the monitor for the slice");
        M->extendTrace(trace_id, e);
    }
}

void HNAMonitor::traceFinished(unsigned trace_id) {
  auto *M = getSlice(trace_id);
  assert(M && "Do not have the monitor for the slice");
  M->traceFinished(trace_id);
}

void HNAMonitor::tracesFinished() {
  _traces_finished = true;
}

