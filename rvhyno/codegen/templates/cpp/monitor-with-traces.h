#ifndef MONITOR_WITH_TRACES_H_
#define MONITOR_WITH_TRACES_H_

#include "monitor.h"
#include "events.h"
#include "traceset.h"

class Stream;

///
// This is a monitor that holds also the traces. (There are also monitors
// that only access the traces stored somewhere else).
class MonitorWithTraces : public Monitor {
protected:
  TraceSet _traces;

public:
  /// adding a new trace to the monitor with ID `id` and with associated stream `stream`
  // Not all traces have to have an associated stream, so this param can be nullptr.
  Trace *newTrace(unsigned trace_id, Stream *stream=nullptr) {
    return _traces.newTrace(trace_id, stream);
  }

  /// Notify that no new trace neither events can come in the future
  void setNoFutureUpdates() {
    _traces.setNoFutureUpdates();
  }

  // Check if the monitor has a trace with ID `trace_id`.
  bool hasTrace(unsigned trace_id) {
    return _traces.hasTrace(trace_id);
  }

};


#endif