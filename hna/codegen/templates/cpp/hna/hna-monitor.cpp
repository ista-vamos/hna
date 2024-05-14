#include <cassert>

#include "hna-monitor.h"

Verdict HNAMonitor::step() {
  Verdict verdict;


  return Verdict::UNKNOWN;
}

SliceTreeNode *HNAMonitor::getSlice(unsigned trace_id) {
    auto it = _trace_to_slice.find(trace_id);
    assert(it != _trace_to_slice.end());

    return it->second;
}

void HNAMonitor::newTrace(unsigned trace_id) {
    assert(_trace_to_monitor.count(trace_id) == 0);

    auto &root = _slices_tree.getRoot();
    root.newTrace(trace_id);
    _trace_to_slice[trace_id] = &root;
}

void HNAMonitor::extendTrace(unsigned trace_id, const ActionEvent &e) {
    auto *N = getSlice(trace_id);
    assert(N && "Do not have the monitor for the slice");

    if (e.isAction()) {
        _trace_to_slice[trace_id] = getOrCreateSlice(N, trace_id, e);
    } else {
        N->extendTrace(trace_id, e.event);
    }
}

SliceTreeNode *HNAMonitor::getOrCreateSlice(SliceTreeNode *current_node, unsigned trace_id, const ActionEvent& e) {
    // get successor node
    auto *succ = _slices_tree.getSuccessor(current_node, e);
    if (!succ) {
        succ = _slices_tree.addSlice(current_node, e);
    }

    assert(!succ->hasTrace(trace_id));
    succ->newTrace(trace_id);

    return succ;
}

void HNAMonitor::traceFinished(unsigned trace_id) {
  auto *N = getSlice(trace_id);
  assert(N && "Do not have the monitor for the slice");
  N->traceFinished(trace_id);
}

void HNAMonitor::tracesFinished() {
  _traces_finished = true;
}

