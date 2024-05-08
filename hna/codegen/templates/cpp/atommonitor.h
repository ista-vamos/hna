#pragma once

#include <algorithm>
#include <cassert>

#include "verdict.h"
#include "hnlcfg.h"

using State = int;

struct EvaluationState {
  State state;
  unsigned short priority;

  // position in the traces
  unsigned p1{0};
  unsigned p2{0};

  EvaluationState(State s, unsigned p1, unsigned p2, unsigned short priority): state(s), priority(priority), p1(p1), p2(p2) {}
};

/**
 * Class representing the evaluation of an atom on a pair of traces
 **/
class AtomMonitor {
protected:
  // which AtomMonitor this is
  const int _type = INVALID;

  const Trace *t1;
  const Trace *t2;

  std::vector<HNLCfg *> _used_by;
  std::vector<EvaluationState> _cfgs;
  // this vector is for the "next states" configurations.
  // we keep it here so that we reuse the allocated memory
  // in between calls to the `step` method.
  std::vector<EvaluationState> _new_cfgs;

  Verdict _result{Verdict::UNKNOWN};

public:
  AtomMonitor(int ty, const Trace *t1, const Trace *t2) : _type(ty), t1(t1), t2(t2) {}

  int type() const { return _type; }

  void setUsedBy(HNLCfg &cfg) {
    _used_by.push_back(&cfg);
  }

  void removeUsedBy(HNLCfg &cfg) {
    auto it = std::find(_used_by.begin(), _used_by.end(), &cfg);
    assert(it != _used_by.end() && "AtomMonitor is not used by the CFG");
    _used_by.erase(it);
    assert(std::find(_used_by.begin(), _used_by.end(), &cfg) == _used_by.end() && "CFG multiple-times in 'used by' the CFG");
  }

  auto used_by_begin() const -> auto { return _used_by.begin(); }
  auto used_by_end() const -> auto { return _used_by.end(); }

  Verdict step(const unsigned step_num);
  Verdict getVerdict() { return _result; }

  /*
  bool finished() const {
    return t1->finished() && t2->finished() &&
            p1 == t1->size() &&
            p2 == t2->size();
  }
  */
};
