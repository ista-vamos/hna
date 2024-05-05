#ifndef TRACESET_H_
#define TRACESET_H_

#include <memory>
#include <mutex>
#include "trace.h"

class TraceSet {
  std::vector<std::unique_ptr<Trace>> _traces;
  std::vector<Trace*> _new_traces;

  std::mutex _traces_mtx;

public:
  // Create a new trace in this TraceSet
  Trace *newTrace();

  // Get a trace created by `newTrace` if there is one.
  // This trace is then 'marked' as not new, and therefore
  // every trace created by `newTrace` is returned by this method
  // exactly once
  Trace *getNewTrace();
};

#endif

