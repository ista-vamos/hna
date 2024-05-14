#pragma once

#include "events.h"

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
