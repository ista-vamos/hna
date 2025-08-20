#ifndef TRACESETBASE_H_
#define TRACESETBASE_H_

#include <map>
#include <memory>
#include <vector>

#include "trace.h"

class TraceSetView;

///
// The base class for TraceSet and SharedTraceSet
class TraceSetBase {
protected:
  // mapping from IDs to traces
  std::map<unsigned, std::unique_ptr<Trace>> _traces;

  // views that should be updated about new traces
  std::vector<TraceSetView *> _views;

public:
  void addView(TraceSetView *);
  void removeView(TraceSetView *);

  virtual bool finished() { return false; }

  auto begin() const -> auto { return _traces.begin(); }
  auto end() const -> auto { return _traces.end(); }
};

#endif
