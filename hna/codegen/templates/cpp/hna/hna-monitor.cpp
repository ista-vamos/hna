#include <cassert>

#ifdef MEASURE_CPUTIME
#include <ctime>
#endif // !MEASURE_CPUTIME


#include "hna-monitor.h"

// generated
#include "do_step.h"

Verdict HNAMonitor::step() {
  if (_result != Verdict::UNKNOWN) {
    return _result;
  }

#ifdef MEASURE_CPUTIME
    struct timespec start, end;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &start);
#endif // !MEASURE_CPUTIME



  Verdict verdict;
  // FIXME: do this event driven -- trace what HNL monitors
  // are waiting for inputs and what have work to do
  // and let the latter do steps (+ those of slices that we
  // updated with events)
  // FIXME: add iterator to SlicesTree
  _slices_tree.ensureNodes();

  for (auto *node : _slices_tree) {
    verdict = do_step(node);
    if (verdict != Verdict::UNKNOWN) {
      #ifdef MEASURE_CPUTIME
      clock_gettime(CLOCK_THREAD_CPUTIME_ID, &end);
      stats.cputime.tv_sec += (end.tv_sec - start.tv_sec);
      stats.cputime.tv_nsec += (end.tv_nsec - start.tv_nsec);
      #endif // !MEASURE_CPUTIME
      return verdict;
    }

    // there will be no future updates,
    // propagate this information to the HNL monitors
    if (_traces_finished) {
      node->noFutureUpdates();
    }
  }

#ifdef MEASURE_CPUTIME
  clock_gettime(CLOCK_THREAD_CPUTIME_ID, &end);
  stats.cputime.tv_sec += (end.tv_sec - start.tv_sec);
  stats.cputime.tv_nsec += (end.tv_nsec - start.tv_nsec);
#endif // !MEASURE_CPUTIME

  return Verdict::UNKNOWN;
}

SliceTreeNode *HNAMonitor::getSlice(unsigned trace_id) {
  auto it = _trace_to_slice.find(trace_id);
  assert(it != _trace_to_slice.end());

  return it->second;
}

void HNAMonitor::newTrace(unsigned trace_id) {
  assert(_trace_to_slice.count(trace_id) == 0);

  auto &root = _slices_tree.getRoot();
  root.newTrace(trace_id);
  _trace_to_slice[trace_id] = &root;
}

void HNAMonitor::extendTrace(unsigned trace_id, const ActionEvent &e) {
  auto *N = getSlice(trace_id);
  assert(N && "Do not have the monitor for the slice");
  assert((N->type != HNANodeType::INVALID) && "Invalid monitor");

  if (e.isAction()) {
    auto *slice = getOrCreateSlice(N, trace_id, e);
    if (!slice) {
      _result = Verdict::FALSE;
      return;
    }
    // in this slice the trace is finished, we continue in the new slice
    N->traceFinished(trace_id);
    _trace_to_slice[trace_id] = slice;
  } else {
    N->extendTrace(trace_id, e.event);
  }
}

SliceTreeNode *HNAMonitor::getOrCreateSlice(SliceTreeNode *current_node,
                                            unsigned trace_id,
                                            const ActionEvent &e) {
  // get successor node
  auto *succ = _slices_tree.getSuccessor(current_node, e);
  if (!succ) {
    succ = _slices_tree.addSlice(current_node, e);
    if (!succ) {
      return nullptr;
    }

    ++stats.num_hnl_monitors;
  }

  assert(!succ->hasTrace(trace_id));
  succ->newTrace(trace_id);

  return succ;
}

void HNAMonitor::traceFinished(unsigned trace_id) {
  auto *N = getSlice(trace_id);
  assert(N && "Do not have the monitor for the slice");
  N->traceFinished(trace_id);
  _trace_to_slice.erase(trace_id);
}

void HNAMonitor::noFutureUpdates() { _traces_finished = true; }
