#include "trace.h"
#include "traceset.h"

Trace *TraceSet::newTrace() {
  _traces.emplace_back(new Trace(_traces.size()));
  return _traces.back().get();
}
