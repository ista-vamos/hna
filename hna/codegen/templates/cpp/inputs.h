#ifndef INPUTS_OD_H
#define INPUTS_OD_H

#include <array>
#include <cstring>
#include <memory>
#include <set>
#include <vector>

#include "trace.h"

#include <vamos-buffers/cpp/event.h>

using vamos::Event;

class Inputs;

///
/// \brief The InputStream class
/// Stream of events that are input to the monitor.
/// This is an opaque object, basically an iterator over incoming events.
/// The incoming events are stored into the trace that is referenced in
/// InputStream.
class InputStream {
protected:
  const size_t _id;
  TraceBase *_trace;
  // this is ugly but efficient, we'll reinterpret cast the data into what we
  // need
  void *_data[4];

  template <typename Ty>
  Ty& data(size_t idx) {
    return *reinterpret_cast<Ty*>(&_data[idx]);
  }

  template <typename Ty>
  const Ty data(size_t idx) const {
    return reinterpret_cast<Ty>(_data[idx]);
  }

  friend class Inputs;

public:
  InputStream(size_t id) : _id(id) {}

  size_t id() const { return _id; }
  void setTrace(TraceBase *t) { _trace = t; }

  TraceBase *trace() { return _trace; }
  const TraceBase *trace() const { return _trace; }

  Event *getEvent();
  const Event *getEvent() const;

  bool hasEvent() const;
  bool isDone() const;
};

class Inputs {
  std::vector<std::unique_ptr<InputStream>> _streams;

  // this is ugly but efficient, we'll reinterpret cast the data into what we
  // need
  void *_data[4];

  template <typename Ty>
  Ty& data(size_t idx) {
    return *reinterpret_cast<Ty*>(&_data[idx]);
  }

  template <typename Ty>
  const Ty data(size_t idx) const {
    return reinterpret_cast<Ty>(_data[idx]);
  }

public:
  Inputs();
  Inputs(char *files[], size_t);

  InputStream *getNewInputStream();
  bool done() const;
};
#endif
