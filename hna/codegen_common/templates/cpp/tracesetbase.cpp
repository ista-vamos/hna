#include <algorithm>
#include <cassert>

#include "tracesetbase.h"

// NOTE: this should not be called concurrently, do not lock
void TraceSetBase::addView(TraceSetView *view) {
  assert(std::find(_views.begin(), _views.end(), view) == _views.end());
  _views.push_back(view);
}

void TraceSetBase::removeView(TraceSetView *view) {
  auto it = std::find(_views.begin(), _views.end(), view);
  assert(it != _views.end());
  _views.erase(it);
}
