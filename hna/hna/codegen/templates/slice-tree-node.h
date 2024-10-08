#ifndef HNA_SLICE_TREE_NODE_H_
#define HNA_SLICE_TREE_NODE_H_

#include <memory>
#include <cassert>

#include "monitor-with-traces.h"
#include "events.h"
#include "hna_node_types.h"

// Monitor + its type. We generate code that uses
// static_cast where the particular type of the monitor is needed
// XXX: in this case using virtual methods could be actually
// very similar in speed, maybe do that to simplify the code?
struct SliceTreeNode {
  std::unique_ptr<MonitorWithTraces> monitor;
  HNANodeType type;

  ~SliceTreeNode();

  SliceTreeNode(SliceTreeNode &&) = default;
  SliceTreeNode(MonitorWithTraces *m, HNANodeType ty) : monitor(m), type(ty) {
    assert(type != HNANodeType::INVALID && "Invalid node type");
  }

  void newTrace(unsigned trace_id);
  void traceFinished(unsigned trace_id);
  void extendTrace(unsigned trace_id, const Event &ev);
  void noFutureUpdates();
  bool hasTrace(unsigned trace_id);
};

#endif // HNA_SLICE_TREE_NODE_H_
