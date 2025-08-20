//#include <chrono>
#include <mutex>
#include <thread>
#include <cassert>

#include "events.h"
#include "trace.h"
#include "traceset.h"

void Trace::lock() {
  /*
      // We expect short waiting times, so use this kind of lock
      // instead of a mutex
      bool unlocked = false;
      if (_lock.compare_exchange_weak(unlocked, true))
          return;

      do {
          unlocked = false;
          std::this_thread::sleep_for(std::chrono::nanoseconds(100));
      // TODO: we could use a weaker memory order
      } while (_lock.compare_exchange_weak(unlocked, true));
      */
  _lock.lock();
}

void Trace::unlock() {
  //_lock = false;
  _lock.unlock();
}

void Trace::append(const Event *e) {
  lock();
  _events.push_back(*e);
  unlock();
}
void Trace::append(const Event &e) {
  lock();
  _events.push_back(e);
  unlock();
}

TraceQuery Trace::get(size_t idx, Event &e) {
  // do not lock the trace if it is finished.
  // This will save a lot of locking.
  // Also, use only the relaxed memory order -- in the worst case,
  // we'll go to the slow code with locking once, but in the future
  // we'll save time by the relaxed reading.
  if (_finished.load(std::memory_order_relaxed)) {
    if (idx < _events.size()) {
        e = _events[idx];
        return TraceQuery::AVAILABLE;
    }
    return TraceQuery::END;
  }

  lock();
  if (idx < _events.size()) {
    e = _events[idx];
    unlock();
    return TraceQuery::AVAILABLE;
  }

  if (_finished) {
    unlock();
    return TraceQuery::END;
  }

  unlock();
  return TraceQuery::WAITING;
}

size_t Trace::size() {
  if (_finished.load(std::memory_order_relaxed)) {
    return _events.size();
  }

  lock();
  auto s = _events.size();
  unlock();
  return s;
}

void Trace::setFinished() {
  _finished = true;
}
bool Trace::finished() {
  return _finished.load(std::memory_order_acquire);
}

void Trace::swap(Trace *rhs) {
    assert(rhs != this);
    lock();
    rhs->lock();

    _events.swap(rhs->_events);

    rhs->unlock();
    unlock();
}

void Trace::copyTo(Trace *rhs) {
    assert(rhs != this);
    lock();
    rhs->lock();

    rhs->_events = _events;
    rhs->_finished.store(_finished);

    rhs->unlock();
    unlock();
}
