#include <chrono>
#include <thread>
#include <mutex>

#include "events.h"
#include "trace.h"
#include "traceset.h"



// We expect short waiting times, so use this kind of lock
// instead of a mutex
void Trace::lock() {
    bool unlocked = false;
    if (_lock.compare_exchange_weak(unlocked, true))
        return;

    do {
        unlocked = false;
        std::this_thread::sleep_for(std::chrono::nanoseconds(100));
    // TODO: we could use a weaker memory order
    } while (_lock.compare_exchange_weak(unlocked, true));
}

void Trace::unlock() {
  _lock = false;
}

void Trace::append(const Event *e) {
    lock();
    _events.push_back(*e);
    unlock();
}
void Trace::append(const Event &e)  {
    lock();
    _events.push_back(e);
    unlock();
}

EventType Trace::get(size_t idx, Event& e) {
    lock();
    if (idx < _events.size()) {
        e = _events[idx];
        unlock();
        return EVENT;
    }

    if (finished()) {
        unlock();
        return END;
    }

    unlock();
    return NONE;
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