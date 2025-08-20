#ifndef MONITOR_WITH_TRACES_H_
#define MONITOR_WITH_TRACES_H_

#include "monitor.h"
#include "events.h"
#include "traceset.h"

///
// This is a monitor that holds also the traces. (There are also monitors
// that only access the traces stored somewhere else).
class MonitorWithTraces : public Monitor {
protected:
  TraceSet _traces;

public:
  /// adding a new trace to the monitor with ID `id`.
  void newTrace(unsigned trace_id) {
    _traces.newTrace(trace_id);
  }

  /// extend the trace with ID `trace_id` with the event `e`
  void extendTrace(unsigned trace_id, const Event &e) {
    _traces.extendTrace(trace_id, e);
  }

  /// Notify the end of the trace
  void traceFinished(unsigned trace_id) {
    _traces.traceFinished(trace_id);
  }

  /// Notify that no new trace neither events can come in the future
  void noFutureUpdates() {
    _traces.noFutureUpdates();
  }

  // Check if the monitor has a trace with ID `trace_id`.
  bool hasTrace(unsigned trace_id) {
    return _traces.hasTrace(trace_id);
  }

};


#endif