#pragma once

#include "verdict.h"
#include "hnlcfg.h"

using State = int;

class AtomMonitor {
protected:
  State _state;

  const Trace *t1;
  const Trace *t2;
  // position in the traces
  size_t p1{0};
  size_t p2{0};

  std::vector<HNLCfg *> _used_by;

  Verdict _result{Verdict::UNKNOWN};

public:
  AtomMonitor(const Trace *t1, const Trace *t2) : t1(t1), t2(t2) {}

  void usedBy(HNLCfg &cfg) {
    _used_by.push_back(&cfg);
  }

  auto used_by_begin() const -> auto { return _used_by.begin(); }
  auto used_by_end() const -> auto { return _used_by.end(); }

  Verdict step(const unsigned step_num);
  Verdict getVerdict() { return _result; }

  bool finished() const {
    return t1->finished() && t2->finished() &&
            p1 == t1->size() &&
            p2 == t2->size();
  }
};
