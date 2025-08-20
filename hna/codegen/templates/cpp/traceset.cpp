#include <algorithm>
#include <cassert>

#include "traceset.h"

TraceSet::~TraceSet() {
  for (auto *view : _views) {
    view->traceSetDestroyed();
  }
}

Trace *TraceSet::newTrace(unsigned trace_id) {
  Trace *t = new Trace(trace_id);

  lock();
  _traces.emplace(trace_id, t);
  unlock();

  // update views with the new trace
  for (auto *view : _views) {
    view->newTrace(trace_id, t);
  }

  return t;
}

void TraceSet::extendTrace(unsigned trace_id, const Event &e) {
  lock();
  Trace *trace = get(trace_id);
  assert(trace && "Do not have such a trace");
  unlock();

  trace->append(e);
}

void TraceSet::traceFinished(unsigned trace_id) {
  lock();
  Trace *trace = get(trace_id);
  assert(trace && "Do not have such a trace");
  trace->setFinished();
  unlock();
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
