#include <mutex>

#include "events.h"
#include "trace.h"
#include "traceset.h"


const Event TraceEnd{};
const Event* TRACE_END = &TraceEnd;

Event *Trace::get(size_t idx) {
    if (idx < _events.size())
        return &_events[idx];
    else if (finished())
        return const_cast<Event *>(&TraceEnd);
    return nullptr;
}

const Event *Trace::get(size_t idx) const {
    if (idx < _events.size())
        return &_events[idx];
    else if (finished())
        return &TraceEnd;
    return nullptr;
}

Trace *TraceSet::newTrace() {
  Trace *t;

  _traces_mtx.lock();
  _new_traces.emplace_back(new Trace(++_trace_id));
  t = _new_traces.back().get();
  _traces_mtx.unlock();

  return t;
}


Trace *TraceSet::getNewTrace() {
  Trace *t = nullptr;

  _traces_mtx.lock();
  if (_new_traces.size() > 0) {
    _traces.push_back(std::move(_new_traces.back()));
    _new_traces.pop_back();

    t = _traces.back().get();
  }
  _traces_mtx.unlock();

  return t;
}