#ifndef ATOM_BASE_H_
#define ATOM_BASE_H_

#include <algorithm>
#include <cassert>
#include <vector>

#include "hnl-state.h"

template <typename HNLInstance> class AtomBase {
protected:
  // which AtomMonitor this is
  const int _type = INVALID;

  std::vector<HNLInstance *> _used_by;

public:
  AtomBase(int ty) : _type(ty) {}

  int type() const { return _type; }

  void setUsedBy(HNLInstance &cfg) { _used_by.push_back(&cfg); }

  void removeUsedBy(HNLInstance &cfg) {
    auto it = std::find(_used_by.begin(), _used_by.end(), &cfg);
    assert(it != _used_by.end() && "AtomMonitor is not used by the CFG");
    _used_by.erase(it);
    assert(std::find(_used_by.begin(), _used_by.end(), &cfg) ==
               _used_by.end() &&
           "CFG multiple-times in 'used by' the CFG");
  }

  auto used_by_begin() const -> auto { return _used_by.begin(); }
  auto used_by_end() const -> auto { return _used_by.end(); }
};

#endif // ATOM_BASE_H_
