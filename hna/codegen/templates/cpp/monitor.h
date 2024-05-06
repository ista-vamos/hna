#ifndef MONITOR_H_
#define MONITOR_H_

#include <vector>

#include "trace.h"
#include "traceset.h"

using State = int;

enum class Verdict : int {
  TRUE = 0,
  FALSE = 1,
  UNKNOWN = 2
};

struct Cfg {
  State s;

  Trace *t1;
  Trace *t2;
  // position in the traces
  size_t p1{0};
  size_t p2{0};

  Cfg(State s0, Trace *t1, Trace *t2) : s(s0), t1(t1), t2(t2) {}

  bool finished() const {
    return t1->finished() && t2->finished() &&
            p1 == t1->size() &&
            p2 == t2->size();
  }
};

class AtomMonitor {
  State _initial_state;
  TraceSet& _traces;
  std::vector<Cfg> _cfgs;

public:
  AtomMonitor(TraceSet& traces, State s0) : _initial_state(s0), _traces(traces) {}

  Verdict step();
};

class HNLMonitor {
  State _initial_state;
  TraceSet& _traces;
  std::vector<Cfg> _cfgs;

public:
  AtomMonitor(TraceSet& traces, State s0) : _initial_state(s0), _traces(traces) {}

  Verdict step();
};


#endif