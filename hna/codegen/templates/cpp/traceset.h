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

  // lock for both, _traces and _new_traces.
  // We could have two locks, one for each container,
  // but my guess is there will be no much difference.
  // Let's have just one and switch to two if profiler
  // tells us it is a bottleneck.
  // Also, in the future we could use some lock-free data structure to keep
  // new traces, e.g., a SPSC lock-free ring-buffer should do.
  std::mutex _traces_mtx;

  // get the trace with the given ID
  // NOTE: lock is not held as this method should not be called
  // concurrently with iterating or modifying the containers
  Trace *get(unsigned trace_id);

  void lock() { _traces_mtx.lock(); }
  void unlock() { _traces_mtx.unlock(); }

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
