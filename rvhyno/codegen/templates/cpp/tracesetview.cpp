#include <cassert>

#include "tracesetview.h"

TraceSetView::TraceSetView(TraceSetBase &S) : traceset(&S) {
  // register this view so that we'll get updated on new traces
  S.addView(this);

  // add all traces that are currently in S between new traces,
  // so that they are returned from `getNewTrace`
  for (auto &[trid, tr_ptr] : S) {
    newTrace(trid, tr_ptr.get());
  }
}

TraceSetView::~TraceSetView() {
  if (!_traceset_destroyed && traceset) {
    traceset->removeView(this);
  }
}

void TraceSetView::traceSetDestroyed() { _traceset_destroyed = true; }

// This view is a view of a single trace only
TraceSetView::TraceSetView(Trace *t) { newTrace(t->id(), t); }

void TraceSetView::newTrace(unsigned trace_id, Trace *tr) {
  lock();
  assert(_traces.count(trace_id) == 0);
  _new_traces.emplace(trace_id, tr);
  unlock();
}

Trace *TraceSetView::getNewTrace() {
  Trace *t = nullptr;

  lock();
  auto trace_it = _new_traces.begin();
  if (trace_it != _new_traces.end()) {
    t = trace_it->second;
    _traces.emplace(t->id(), t);
    _new_traces.erase(trace_it);
  }
  unlock();

  return t;
}

Trace *TraceSetView::get(unsigned trace_id) {
  auto it = _traces.find(trace_id);
  if (it != _traces.end()) {
    auto *ret = it->second;
    return ret;
  }

  it = _new_traces.find(trace_id);
  if (it != _new_traces.end()) {
    auto *ret = it->second;
    return ret;
  }

  return nullptr;
}

bool TraceSetView::hasTrace(unsigned trace_id) {
  bool ret;
  lock();
  ret = (get(trace_id) != nullptr);
  unlock();

  return ret;
}

bool TraceSetView::finished() {
    lock();
    bool no_new_traces = _new_traces.empty();
    unlock();

    if (!no_new_traces) {
      return false;
    }

    if (traceset) {
      assert(!_traceset_destroyed);
      return traceset->finished();
    }

    assert(_traces.size() != 0);
    assert(_traces.size() == 1);
    return _traces.begin()->second->finished();
  }

/*
bool TraceSetView::allTracesFinished() {
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
*/
