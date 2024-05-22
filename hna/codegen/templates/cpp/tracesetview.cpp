#include <cassert>

#include "tracesetview.h"


// NOTE: we do not lock anything as there should be no concurrency here.

TraceSetView::TraceSetView(TraceSet& S) : traceset(&S) {
    // register this view so that we'll get updated on new traces
    S.addView(this);

    for (auto& [trid, tr_ptr] : S) {
        newTrace(trid, tr_ptr.get());
    }
}

TraceSetView::~TraceSetView() {
    if (traceset) {
        traceset->removeView(this);
    }
}

// This view is a view of a single trace only
TraceSetView::TraceSetView(Trace *t) {
    newTrace(t->id(), t);
}

void TraceSetView::newTrace(unsigned trace_id, Trace *tr) {
  //_traces_mtx.lock();
  _new_traces.emplace(trace_id, tr);
  //_traces_mtx.unlock();
}

Trace *TraceSetView::getNewTrace() {
  Trace *t = nullptr;

  //_traces_mtx.lock();
  auto trace_it = _new_traces.begin();
  if (trace_it != _new_traces.end()) {
    t = trace_it->second;
    _traces.emplace(t->id(), t);
    _new_traces.erase(trace_it);
  }
  //_traces_mtx.unlock();

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
    //_traces_mtx.lock();
    ret = (get(trace_id) != nullptr);
    //_traces_mtx.unlock();

    return ret;
}

bool TraceSetView::allTracesFinished() {
    //_traces_mtx.lock();
    if (_new_traces.size() > 0) {
        //_traces_mtx.unlock();
        return false;
    }

    for (auto &it : _traces) {
        if (!it.second->finished()) {
            //_traces_mtx.unlock();
            return false;
        }
    }

    //_traces_mtx.unlock();
    return true;
}
