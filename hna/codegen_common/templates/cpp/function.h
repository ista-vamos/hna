#ifndef HNL_FUNCTION_H_
#define HNL_FUNCTION_H_

#include "traceset.h"

class Function {
public:
  virtual ~Function() {}

  virtual void step() = 0;
  virtual bool noFutureUpdates() const = 0;
};

#endif // HNL_FUNCTION_H_
