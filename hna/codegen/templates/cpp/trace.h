#ifndef TRACE_H
#define TRACE_H

#include <vector>

#include "events.h"

class Trace {
  const size_t _id;
  bool _finished{false};
  std::vector<Event> _events;

public:
  Trace(size_t id) : _id(id) {}

  void setFinished() { _finished = true; }
  bool finished() const { return _finished; }
  size_t id() const { return _id; }

  void append(const Event *e) { _events.push_back(*e); }
  void append(const Event &e) { _events.push_back(e); };

  Event *get(size_t idx) { return &_events[idx]; }
  const Event *get(size_t idx) const { return &_events[idx]; }

  Event *try_get(size_t idx) {
    if (idx < _events.size())
        return &_events[idx];
     return nullptr;
  }
  const Event *try_get(size_t idx) const {
    if (idx < _events.size())
        return &_events[idx];
     return nullptr;
  }

  Event *operator[](size_t idx) { return get(idx); }
  const Event *operator[](size_t idx) const { return get(idx); }

  size_t size() const { return _events.size(); }
};

#endif
