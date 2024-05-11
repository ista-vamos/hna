#pragma once

#include <algorithm>
#include <vector>
#include <cassert>

#include "verdict.h"
#include "hnlcfg.h"

using State = int;

struct EvaluationState {
  State state;

  // position in the traces
  unsigned p1{0};
  unsigned p2{0};

  EvaluationState(State s, unsigned p1, unsigned p2): state(s), p1(p1), p2(p2) {}
};

/**
 * This is a vector where new elements are pushed into a separate
 * storage and are moved to the main storage only on an explicit call.
 * This is because we iterate over the vector when adding.
 */
class EvaluationStateSet : public std::vector<EvaluationState> {
  std::vector<EvaluationState> _new_cfgs;

public:
  void emplace_new(State s, unsigned p1, unsigned p2) {
    _new_cfgs.emplace_back(s, p1, p2);
  }

  auto back_new() -> auto { return _new_cfgs.back(); }

  template <typename Arg>
  void push_new(Arg a) {
    _new_cfgs.push_back(a);
  }

  void new_to_this() {
    insert(begin(), _new_cfgs.begin(), _new_cfgs.end());
    _new_cfgs.clear();
  }

  void rotate() {
    clear();
    new_to_this();
  }

};

/**
 * Class representing the evaluation of an atom on a pair of traces
 **/
class AtomMonitor {
protected:
  // which AtomMonitor this is
  const int _type = INVALID;

  Trace *t1;
  Trace *t2;

  std::vector<HNLInstance *> _used_by;
  EvaluationStateSet _cfgs;

  Verdict _result{Verdict::UNKNOWN};

public:
  AtomMonitor(int ty, Trace *t1, Trace *t2) : _type(ty), t1(t1), t2(t2) {}

  int type() const { return _type; }

  void setUsedBy(HNLInstance &cfg) {
    _used_by.push_back(&cfg);
  }

  void removeUsedBy(HNLInstance &cfg) {
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
