#include "traceset.h"

Trace *TraceSet::newTrace(unsigned trace_id) {
  Trace *t;

  _traces_mtx.lock();
  _new_traces.emplace_back(new Trace(trace_id));
  t = _new_traces.back().get();
  _traces_mtx.unlock();

  return t;
}


Trace *TraceSet::getNewTrace() {
  Trace *t = nullptr;

  _traces_mtx.lock();
  if (_new_traces.size() > 0) {
    auto& trace_ptr = _new_traces.back();
    t = trace_ptr.get();

    _traces.emplace(trace_ptr->id(), std::move(trace_ptr));
    _new_traces.pop_back();
  }
  _traces_mtx.unlock();

  return t;
}

Trace *TraceSet::get(unsigned trace_id) const {
    // FIXME: use a small local cache of last say 4 lookups?
    auto it = _traces.find(trace_id);
    if (it == _traces.end()) {
        return nullptr;
    }

    return it->second.get();
}
