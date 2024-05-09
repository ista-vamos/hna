#ifndef TRACE_H
#define TRACE_H

#include <vector>
#include <atomic>

#include "events.h"

enum EventType {
    // no available event
    NONE,
    // available event
    EVENT,
    // trace ended (end event)
    END
};

class Trace {
  const size_t _id;
  bool _finished{false};
  std::vector<Event> _events;
  // the trace is being read and allocated at the same time,
  // so we must lock it
  // (at least until it is finished -- in the future we might
  //  improve the implementation)
  std::atomic<bool> _lock{false};

  void lock();
  void unlock();

public:
  Trace(size_t id) : _id(id) {}

  size_t id() const { return _id; }

  void append(const Event *e);
  void append(const Event &e);

  EventType get(size_t idx, Event&);

  // NOTE: these are unlocked
  size_t size() const { return _events.size(); }
  void setFinished() { _finished = true; }
  bool finished() const { return _finished; }
};

#endif
