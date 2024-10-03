#ifndef TRACESET_H_
#define TRACESET_H_

#include <atomic>
#include <map>
#include <memory>
#include <mutex>
#include <vector>

#include "tracesetbase.h"
#include "trace.h"

class TraceSetView;

///
// The class for storing observation traces.
// Unlike SharedTraceSet which is sequential, this class
// supports parallel addition or traces, their updates and querying.
class TraceSet : public TraceSetBase {
  std::map<unsigned, std::unique_ptr<Trace>> _new_traces;

  std::atomic<bool> _traces_finished{false};

  std::mutex _traces_mtx;

  // get the trace with the given ID
  // NOTE: lock is not held as this method should not be called
  // concurrently with iterating or modifying the containers
  Trace *get(unsigned trace_id);

  void lock() { _traces_mtx.lock(); }
  void unlock() { _traces_mtx.unlock(); }

public:
  // Create a new trace in this TraceSet.
  Trace *newTrace(unsigned trace_id);

  void extendTrace(unsigned trace_id, const Event &e);
  void traceFinished(unsigned trace_id);

  // Get some trace previously created by `newTrace` (if there is one).
  // Every trace created by `newTrace` is marked as _new_.
  // When it is returned by this method, the trace is marked as not new,
  // and therefore every trace created by `newTrace` is returned by this method
  // only once.
  //
  // This method modifies both, _traces and _new_traces (under the lock).
  // Our code never iterates over traces and calls this method at the same
  // time, so there is no race while iterating unlocked over traces.
  Trace *getNewTrace();

  // set that there will be no new traces nor events in the future
  void noFutureUpdates() {
    _traces_finished.store(true, std::memory_order_release);
  }

  bool finished() override {
    bool r = _traces_finished.load(std::memory_order_acquire);
    if (r) {
      lock();
      r = _new_traces.empty();
      unlock();
    }
    return r;
  }

  // check if the finished flag is set for all the traces
  bool allTracesFinished();

  bool hasTrace(unsigned trace_id);

  size_t size();
};

#endif
