#ifndef TRACESETBASE_H_
#define TRACESETBASE_H_

#include <map>
#include <memory>
#include <mutex>
#include <vector>

#include "trace.h"

class TraceSetView;

///
// The base class for TraceSet and SharedTraceSet
class TraceSetBase {
protected:
  // mapping from IDs to traces
  std::map<unsigned, std::unique_ptr<Trace>> _traces;

  // views that should be updated about new traces
  std::vector<TraceSetView *> _views;

  // The ctor of `TraceSetView` calls `addView`.
  // If, at the same time, `newTrace` iterates over `_views`,
  // we have a problem. Therefore, we need a lock (at least for now).
  //
  // Notice that the problem is that `newTrace` and `addView` can be called
  // concurrently by the monitoring code and the CSV reader,
  // so when this object is `TraceSet`.
  // In `SharedTraceSet` this is not a problem.
  std::mutex _views_mtx;

  // lock for both, _traces and _new_traces.
  // We could have two locks, one for each container,
  // but my guess is there will be no much difference.
  // Let's have just one and switch to two if profiler
  // tells us it is a bottleneck.
  // Also, in the future we could use some lock-free data structure to keep
  // new traces, e.g., a SPSC lock-free ring-buffer should do.
  std::mutex _traces_mtx;

public:
  void lock() { _traces_mtx.lock(); }
  void unlock() { _traces_mtx.unlock(); }
  void lock_views() { _views_mtx.lock(); }
  void unlock_views() { _views_mtx.unlock(); }

  void addView(TraceSetView *);
  void removeView(TraceSetView *);

  virtual bool finished() { return false; }

  auto begin() const -> auto { return _traces.begin(); }
  auto end() const -> auto { return _traces.end(); }
};

#endif
