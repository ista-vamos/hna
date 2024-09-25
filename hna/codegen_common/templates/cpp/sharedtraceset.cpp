#include <algorithm>
#include <cassert>

#include "sharedtraceset.h"
#include "tracesetview.h"

SharedTraceSet::~SharedTraceSet() {
  for (auto *view : _views) {
    view->traceSetDestroyed();
  }
}

Trace *SharedTraceSet::newTrace(unsigned trace_id) {
  Trace *t = _traces.emplace(trace_id, new Trace(trace_id)).first->second.get();

  // update views with the new trace
  for (auto *view : _views) {
    view->newTrace(trace_id, t);
  }

  return t;
}

void SharedTraceSet::extendTrace(unsigned trace_id, const Event &e) {
  Trace *trace = get(trace_id);
  assert(trace && "Do not have such a trace");
  trace->append(e);
}

void SharedTraceSet::traceFinished(unsigned trace_id) {
  Trace *trace = get(trace_id);
  assert(trace && "Do not have such a trace");
  trace->setFinished();
}

Trace *SharedTraceSet::get(unsigned trace_id) {
  auto it = _traces.find(trace_id);
  if (it != _traces.end()) {
    return it->second.get();
  }

  return nullptr;
}

bool SharedTraceSet::hasTrace(unsigned trace_id) {
  return get(trace_id) != nullptr;
}

bool SharedTraceSet::allTracesFinished() {
  for (auto &it : _traces) {
    if (!it.second->finished()) {
      return false;
    }
  }

  return true;
}

// NOTE: this should not be called concurrently, do not lock
void SharedTraceSet::addView(TraceSetView *view) {
  assert(std::find(_views.begin(), _views.end(), view) == _views.end());
  _views.push_back(view);
}

void SharedTraceSet::removeView(TraceSetView *view) {
  auto it = std::find(_views.begin(), _views.end(), view);
  assert(it != _views.end());
  _views.erase(it);
}
