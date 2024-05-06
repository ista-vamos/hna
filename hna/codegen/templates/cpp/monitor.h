#ifndef MONITOR_H_
#define MONITOR_H_

#include <vector>

#include "trace.h"
#include "traceset.h"

enum class Verdict : int {
  TRUE = 0,
  FALSE = 1,
  UNKNOWN = 2
};

struct Cfg {
  Trace *trace;
  size_t pos{0};

  Cfg(Trace *t) : trace(t) {}

  bool finished() const {
    return trace->finished() && pos == trace->size();
  }
};

class HNLMonitor {
  TraceSet& _traces;
  std::vector<Cfg> _cfgs;

public:
  HNLMonitor(TraceSet& traces) : _traces(traces) {}

  Verdict step();
};


#endif