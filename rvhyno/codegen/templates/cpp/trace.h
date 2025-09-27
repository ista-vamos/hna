#ifndef TRACE_H
#define TRACE_H

#include <atomic>
#include <mutex>
#include <vector>
#include <cassert>

#include "stream.h"
#include "events.h"

enum class TraceQuery {
  // no available event
  WAITING,
  // available event
  AVAILABLE,
  // trace ended (end event)
  END
};

class Trace {
  // ID of the trace
  const size_t _id;
  // the stream this traces reads from
  // TODO: split Trace into multiple child classes, having a stream
  // is just one option.
  Stream *_stream;

  std::atomic<bool> _finished{false};
  std::vector<Event> _events;
  // the trace is being read and allocated at the same time,
  // so we must lock it
  // (at least until it is finished -- in the future we might
  //  improve the implementation)
  // std::atomic<bool> _lock{false};
  std::mutex _lock;

  void lock();
  void unlock();

  std::string _descr;

public:
  Trace(size_t id, Stream *stream)
  : _id(id), _stream(stream) {
    assert(id > 0);
    assert(stream != nullptr);

    _descr = "Trace " + std::to_string(_id) + ": " + _stream->descr();
  }

  Stream *stream() const { return _stream; }

  size_t id() const { return _id; }

  void append(const Event *e);
  void append(const Event &e);

  TraceQuery get(size_t idx, Event &);

  size_t size();
  void setFinished();
  bool finished();

  void swap(Trace *);
  void copyTo(Trace *);


  // FIXME: remove
  std::vector<Event>& events() { return _events; }
  const std::vector<Event>& events() const { return _events; }

  const std::string& descr() const { return _descr; }
};

#endif
