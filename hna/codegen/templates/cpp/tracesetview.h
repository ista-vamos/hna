#ifndef TRACESETVIEW_H_
#define TRACESETVIEW_H_

#include <map>
#include <memory>
#include <mutex>
#include <vector>

#include "sharedtraceset.h"
#include "trace.h"

// trace set that only references traces from some other (shared) trace set
// (or references a single trace from some trace set)
class TraceSetView {
  SharedTraceSet *traceset{nullptr};
  bool _traceset_destroyed{false};

  // mapping from IDs to traces
  std::map<unsigned, Trace *> _traces;
  std::map<unsigned, Trace *> _new_traces;

  // std::mutex _traces_mtx;

  // get the trace with the given ID
  // NOTE: lock is not held as this method should not be called
  // concurrently with iterating over _traces
  Trace *get(unsigned trace_id);

public:
  TraceSetView() = default;
  ~TraceSetView();
  TraceSetView(SharedTraceSet &);
  TraceSetView(Trace *);

  bool finished() const {
    if (!_new_traces.empty()) {
      return false;
    }

    if (traceset) {
      assert(!_traceset_destroyed);
      return traceset->finished();
    }

    assert(_traces.size() != 0);
    assert(_traces.size() == 1);
    return _traces.begin()->second->finished();
  }

  // Announce a new trace in this SharedTraceSet.
  void newTrace(unsigned trace_id, Trace *);

  // Get a trace announced by `newTrace` if there is one.
  // This trace is then 'marked' as not new, and therefore
  // every trace announced via `newTrace` is returned by this method
  // exactly once.
  //
  // This method modifies both, _traces and _new_traces (under the lock).
  // Our code never iterates over traces and calls this method at the same
  // time, so there is no race while iterating unlocked over traces.
  Trace *getNewTrace();

  void traceSetDestroyed();

  // check if the finished flag is set for all the traces
  bool allTracesFinished();

  bool hasTrace(unsigned trace_id);

  auto begin() const -> auto { return _traces.begin(); }
  auto end() const -> auto { return _traces.end(); }
};

#endif
