#pragma once

#include "events.h"

///
// This is the interface for monitors. The methods are not virtual
// intentionally, the monitors will not be used through this class.
// The methods here just give the interface.
class Monitor {
public:
  /// adding a new trace to the monitor with ID `id`.
  /// Additionally, `set_id` my be set if traces come from
  /// multiple sets of traces. We still require that `trace_id`
  /// is unique, no matter what is `set_id` (this is subject to change).
  void newTrace(unsigned trace_id, unsigned set_id = 0);

  /// extend the trace with ID `trace_id` with the event `e`
  void extendTrace(unsigned trace_id, const Event &e);

  /// Notify the end of the trace
  void traceFinished(unsigned trace_id);

  /// Notify that no new trace neither events can come in the future
  void noFutureUpdates(unsigned trace_id);
};

