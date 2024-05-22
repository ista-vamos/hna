#ifndef TRACESET_H_
#define TRACESET_H_

#include <memory>
#include <mutex>
#include <map>
#include <vector>

#include "trace.h"

class TraceSetView;

class TraceSet {
  // mapping from IDs to traces
  std::map<unsigned, std::unique_ptr<Trace>> _traces;
  std::map<unsigned, std::unique_ptr<Trace>> _new_traces;

  // views that should be updated about new traces
  std::vector<TraceSetView *> _views;

  std::mutex _traces_mtx;

  // get the trace with the given ID
  // NOTE: lock is not held as this method should not be called
  // concurrently with iterating over _traces
  Trace *get(unsigned trace_id);

public:
  // Create a new trace in this TraceSet.
  Trace *newTrace(unsigned trace_id);

  void extendTrace(unsigned trace_id, const Event &e);
  void traceFinished(unsigned trace_id);

  // Get a trace created by `newTrace` if there is one.
  // This trace is then 'marked' as not new, and therefore
  // every trace created by `newTrace` is returned by this method
  // exactly once.
  //
  // This method modifies both, _traces and _new_traces (under the lock).
  // Our code never iterates over traces and calls this method at the same
  // time, so there is no race while iterating unlocked over traces.
  Trace *getNewTrace();

  // check if the finished flag is set for all the traces
  bool allTracesFinished();

  bool hasTrace(unsigned trace_id);

  void addView(TraceSetView *);
  void removeView(TraceSetView *);

  auto begin() const -> auto { return _traces.begin(); }
  auto end() const -> auto { return _traces.end(); }
};

#endif

