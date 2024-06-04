#ifndef STREAM_H_
#define STREAM_H_

#include "events.h"

class Stream {
  using IDTy = unsigned;
  const IDTy _id;

public:
  Stream(IDTy trace_id) : _id(trace_id) {}

  IDTy id() const { return _id; }
  // Not implemented -- the child classes need to implement it
  // NOTE: these methods are not virtual intentionally,
  // they are here just to have the full interface for child classes,
  // but we do not plan to use this class to dispatch calls for subclasses.
  bool try_read(Event &ev);
  bool finished() const;
};

#endif  // STREAM_H_
