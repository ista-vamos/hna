#include <mutex>

#include "trace.h"
#include "traceset.h"

Trace *TraceSet::newTrace() {
  _traces.emplace_back(new Trace(_traces.size()));
  auto *t = _traces.back().get();

  _traces_mtx.lock();
  _new_traces.push_back(t);
  _traces_mtx.unlock();

  return t;
}


Trace *TraceSet::getNewTrace() {
  Trace *t = nullptr;

  _traces_mtx.lock();
  if (_new_traces.size() > 0) {
    t = _new_traces.back();
    _new_traces.pop_back();
  }
  _traces_mtx.unlock();

  return t;
}