#ifndef SHAREDTRACESET_H_
#define SHAREDTRACESET_H_

#include <atomic>
#include <map>
#include <memory>
#include <mutex>
#include <vector>

#include "tracesetbase.h"

class TraceSetView;

// TraceSet that can be accessed only via views (read-only object that
// work as TraceSet but do not store the traces in them).
// It is not concurrent -- we never modify and read it in parallel.
class SharedTraceSet : public TraceSetBase {
  bool _traces_finished{false};

public:
  SharedTraceSet() = default;
  SharedTraceSet(SharedTraceSet&&) = default;
  SharedTraceSet& operator=(SharedTraceSet&&) = default;
  ~SharedTraceSet();

  // get the trace with the given ID
  Trace *get(unsigned trace_id);

  // Create a new trace in this SharedTraceSet.
  Trace *newTrace(unsigned trace_id);

  void extendTrace(unsigned trace_id, const Event &e);
  void traceFinished(unsigned trace_id);

  void noFutureUpdates() { _traces_finished = true; }
  bool finished() override { return _traces_finished; }

  // check if the finished flag is set for all the traces
  // bool allTracesFinished();

  bool hasTrace(unsigned trace_id);
};

#endif
