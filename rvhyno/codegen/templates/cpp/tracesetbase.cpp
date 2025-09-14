#include <algorithm>
#include <cassert>

#include "tracesetbase.h"

void TraceSetBase::addView(TraceSetView *view) {
  lock_views();
  assert(std::find(_views.begin(), _views.end(), view) == _views.end());
  _views.push_back(view);
  unlock_views();
}

void TraceSetBase::removeView(TraceSetView *view) {
  lock_views();
  auto it = std::find(_views.begin(), _views.end(), view);
  assert(it != _views.end());
  _views.erase(it);
  unlock_views();
}
