#include <algorithm>
#include <cassert>

#include "traceset.h"
#include "tracesetview.h"

Trace *TraceSet::newTrace(unsigned trace_id) {
  Trace *t;

  _traces_mtx.lock();
  t = _new_traces.emplace(trace_id, new Trace(trace_id)).first->second.get();
  _traces_mtx.unlock();

  // update views with the new trace
  for (auto *view : _views) {
    view->newTrace(trace_id, t);
  }

  return t;
}


Trace *TraceSet::getNewTrace() {
  Trace *t = nullptr;

  _traces_mtx.lock();
  auto trace_it = _new_traces.begin();
  if (trace_it != _new_traces.end()) {
    t = trace_it->second.get();

    _traces.emplace(t->id(), std::move(trace_it->second));
    _new_traces.erase(trace_it);
  }
  _traces_mtx.unlock();

  return t;
}

void TraceSet::extendTrace(unsigned trace_id, const Event &e) {
    _traces_mtx.lock();
    Trace *trace = get(trace_id);
    assert(trace && "Do not have such a trace");
    _traces_mtx.unlock();

    trace->append(e);
}

void TraceSet::traceFinished(unsigned trace_id) {
  _traces_mtx.lock();
  Trace *trace = get(trace_id);
  assert(trace && "Do not have such a trace");
  trace->setFinished();
  _traces_mtx.unlock();
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
    _traces_mtx.lock();
    ret = (get(trace_id) != nullptr);
    _traces_mtx.unlock();

    return ret;
}

bool TraceSet::allTracesFinished() {
    _traces_mtx.lock();
    if (_new_traces.size() > 0) {
        _traces_mtx.unlock();
        return false;
    }

    for (auto &it : _traces) {
        if (!it.second->finished()) {
            _traces_mtx.unlock();
            return false;
        }
    }

    _traces_mtx.unlock();
    return true;
}


// NOTE: this should not be called concurrently, do not lock
void TraceSet::addView(TraceSetView *view) {
    assert(std::find(_views.begin(), _views.end(), view) == _views.end());
    _views.push_back(view);
}

void TraceSet::removeView(TraceSetView *view) {
    auto it = std::find(_views.begin(), _views.end(), view);
    assert (it != _views.end());
    _views.erase(it);
}

