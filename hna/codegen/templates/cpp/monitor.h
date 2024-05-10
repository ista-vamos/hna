#ifndef MONITOR_H_
#define MONITOR_H_

#include <vector>
#include <list>

#include "trace.h"
#include "traceset.h"
#include "verdict.h"
#include "atommonitor.h"

/* generated */
#include "hnlcfg.h"


class HNLMonitor {
  TraceSet& _traces;
  std::vector<std::unique_ptr<HNLCfg>> _cfgs;
  std::list<std::unique_ptr<AtomMonitor>> _atom_monitors;

public:
  HNLMonitor(TraceSet& traces) : _traces(traces) {}

  AtomMonitor *createAtomMonitor(Action monitor_type, HNLCfg&);
  void removeCfg(HNLCfg *cfg);
  void removeAtomMonitor(AtomMonitor *M);

  Verdict step();
};


#endif