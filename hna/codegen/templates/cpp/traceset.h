#ifndef TRACESET_H_
#define TRACESET_H_

#include <memory>
#include "trace.h"

class TraceSet {
  std::vector<std::unique_ptr<Trace>> _traces;

public:
  Trace *newTrace();

};

#endif

