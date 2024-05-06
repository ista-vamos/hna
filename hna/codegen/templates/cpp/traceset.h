#ifndef TRACESET_H_
#define TRACESET_H_

#include <memory>
#include <mutex>
#include "trace.h"

class TraceSet {
  size_t _trace_id{0};
  std::vector<std::unique_ptr<Trace>> _traces;
  std::vector<std::unique_ptr<Trace>> _new_traces;

  std::mutex _traces_mtx;

public:
  // Create a new trace in this TraceSet.
  Trace *newTrace();

  // Get a trace created by `newTrace` if there is one.
  // This trace is then 'marked' as not new, and therefore
  // every trace created by `newTrace` is returned by this method
  // exactly once.
  //
  // This method modifies both, _traces and _new_traces (under the lock).
  // Our code never iterates over traces and calls this method at the same
  // time, so there is no race while iterating unlocked over traces.
  Trace *getNewTrace();

  auto begin() const -> auto { return _traces.begin(); }
  auto end() const -> auto { return _traces.end(); }
};

#endif

