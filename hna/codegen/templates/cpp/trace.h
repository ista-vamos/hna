#ifndef TRACE_H
#define TRACE_H

#include <vector>

#include "events.h"

extern const Event TraceEnd;
extern const Event* TRACE_END;


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

  Event *get(size_t idx);
  const Event *get(size_t idx) const;

  Event *operator[](size_t idx) { return get(idx); }
  const Event *operator[](size_t idx) const { return get(idx); }

  size_t size() const { return _events.size(); }
};

#endif
