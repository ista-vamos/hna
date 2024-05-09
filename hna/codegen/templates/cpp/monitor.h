#ifndef MONITOR_H_
#define MONITOR_H_

#include <vector>

#include "trace.h"
#include "traceset.h"
#include "verdict.h"
#include "atommonitor.h"

/* generated */
#include "hnlcfg.h"


class HNLMonitor {
  TraceSet& _traces;
  std::vector<std::unique_ptr<HNLCfg>> _cfgs;
  std::vector<std::unique_ptr<AtomMonitor>> _atom_monitors;

public:
  HNLMonitor(TraceSet& traces) : _traces(traces) {}

  AtomMonitor *createAtomMonitor(Action monitor_type, HNLCfg&);

  Verdict step();
};


#endif