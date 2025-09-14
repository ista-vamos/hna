#ifndef TRACESET_H_
#define TRACESET_H_

#include <atomic>
#include <map>
#include <memory>
#include <mutex>
#include <vector>

#include "tracesetbase.h"
#include "tracesetview.h"
#include "trace.h"

class TraceSetView;

///
// The class for storing observation traces.
// Unlike SharedTraceSet which is sequential, this class
// supports parallel addition or traces, their updates and querying.
class TraceSet : public TraceSetBase {

  std::atomic<bool> _traces_finished{false};

  // get the trace with the given ID
  // NOTE: lock is not held as this method should not be called
  // concurrently with iterating or modifying the containers
  Trace *get(unsigned trace_id);

public:
  TraceSet() = default;
  ~TraceSet();

  // Create a new trace in this TraceSet.
  Trace *newTrace(unsigned trace_id);

  void extendTrace(unsigned trace_id, const Event &e);
  void traceFinished(unsigned trace_id);

  // set that there will be no new traces nor events in the future
  void noFutureUpdates() {
    _traces_finished.store(true, std::memory_order_release);
  }

  bool finished() override {
    return _traces_finished.load(std::memory_order_acquire);
  }

  bool hasTrace(unsigned trace_id);

  size_t size();
};

#endif
