#include <atomic>

#include "hnl-monitor-base.h"
#include "traceset.h"

void HNLMonitorBase::newTrace(unsigned trace_id) {
    _traces.newTrace(trace_id);
}

void HNLMonitorBase::extendTrace(unsigned trace_id, const Event &e) {
    _traces.extendTrace(trace_id, e);
}

void HNLMonitorBase::traceFinished(unsigned trace_id) {
  _traces.traceFinished(trace_id);
}

void HNLMonitorBase::tracesFinished() {
  _traces_finished.store(true, std::memory_order_release);
}

bool HNLMonitorBase::allTracesFinished() {
    return _traces.allTracesFinished();
}

bool HNLMonitorBase::hasTrace(unsigned trace_id) {
    return _traces.hasTrace(trace_id);
}