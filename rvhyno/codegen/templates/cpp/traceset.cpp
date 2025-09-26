#include <cassert>

#include "traceset.h"


TraceSet::~TraceSet() {
  // when a trace set is being destroyed, no new
  // views should be added or removed, so hold no lock
  for (auto *view : _views) {
    view->traceSetDestroyed();
  }
}


Trace *TraceSet::newTrace(unsigned trace_id, Stream *stream) {
  Trace *t = new Trace(trace_id, stream);

  lock();
  _traces.emplace(trace_id, t);
  unlock();

  // update views with the new trace
  lock_views();
  for (auto *view : _views) {
    view->newTrace(trace_id, t);
  }
  unlock_views();

  return t;
}


Trace *TraceSet::get(unsigned trace_id) {
  auto it = _traces.find(trace_id);
  if (it != _traces.end()) {
    auto *ret = it->second.get();
    return ret;
  }

  return nullptr;
}


bool TraceSet::hasTrace(unsigned trace_id) {
  bool ret;
  lock();
  ret = (get(trace_id) != nullptr);
  unlock();

  return ret;
}


size_t TraceSet::size() {
  size_t ret;
  lock();
  ret = _traces.size();
  unlock();

  return ret;
}
