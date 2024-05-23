#include <algorithm>
#include <cassert>

#include "traceset.h"

Trace *TraceSet::newTrace(unsigned trace_id) {
  Trace *t;

  lock();
  t = _new_traces.emplace(trace_id, new Trace(trace_id)).first->second.get();
  unlock();

  return t;
}

Trace *TraceSet::getNewTrace() {
  Trace *t = nullptr;

  lock();
  auto trace_it = _new_traces.begin();
  if (trace_it != _new_traces.end()) {
    t = trace_it->second.get();

    _traces.emplace(t->id(), std::move(trace_it->second));
    _new_traces.erase(trace_it);
  }
  unlock();

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

  it = _new_traces.find(trace_id);
  if (it != _new_traces.end()) {
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

bool TraceSet::allTracesFinished() {
  lock();
  if (_new_traces.size() > 0) {
    unlock();
    return false;
  }

  for (auto &it : _traces) {
    if (!it.second->finished()) {
      unlock();
      return false;
    }
  }

  unlock();
  return true;
}
