#ifndef HNL_SUB_MONITOR_BASE_
#define HNL_SUB_MONITOR_BASE_

#include "monitor.h"

class HNLSubMonitorBase : public Monitor {
public:
   // check for new traces and create HNLInstances for them
  // if there are some
  virtual bool addNewTraces();
};

#endif // HNL_SUB_MONITOR_BASE_
