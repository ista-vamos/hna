#include <chrono>
#include <thread>
#include <mutex>

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

    if (_finished) {
        unlock();
        return END;
    }

    unlock();
    return NONE;
}



size_t Trace::size() {
    lock();
    auto s = _events.size();
    unlock();
    return s;
}
void Trace::setFinished() { lock(); _finished = true; unlock(); }
bool Trace::finished() { lock(); auto f = _finished; unlock(); return f;}
