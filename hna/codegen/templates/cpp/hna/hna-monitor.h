#ifndef HNA_MONITOR_H_
#define HNA_MONITOR_H_

#include <list>
#include <memory>
#include <vector>

#include "hnl-monitor-base.h"
#include "trace.h"
#include "traceset.h"
#include "verdict.h"

// generated
#include "events.h"
#include "hna_node_types.h"
#include "hnl-monitors.h"

// Monitor + its type. We generate code that uses
// static_cast where the particular type of the monitor is needed
// XXX: in this case using virtual methods could be actually
// very similar in speed, maybe do that to simplify the code?
struct SliceTreeNode {
  std::unique_ptr<HNLMonitorBase> monitor;
  HNANodeType type;

  ~SliceTreeNode(){
// we need to cast the unique_ptr to the right type
// so that the right dtor is called
#include "slice-tree-node-dtor.h"
  }

  SliceTreeNode(SliceTreeNode &&) = default;
  SliceTreeNode(HNLMonitorBase *m, HNANodeType ty) : monitor(m), type(ty) {
    assert(type != HNANodeType::INVALID && "Invalid node type");
  }

  void newTrace(unsigned trace_id) { monitor->newTrace(trace_id); }

  void traceFinished(unsigned trace_id) { monitor->traceFinished(trace_id); }

  void extendTrace(unsigned trace_id, const Event &ev) {
    monitor->extendTrace(trace_id, ev);
  }

  void noFutureUpdates() { monitor->noFutureUpdates(); }

  bool hasTrace(unsigned trace_id) { return monitor->hasTrace(trace_id); }
};

class SlicesTree {
  SliceTreeNode root;
  // We do not necessarily need this, but iterating over the vector
  // is faster (and easier) than iterating over _edges + root.
  // std::vector<Monitor *> _monitors;
  std::vector<SliceTreeNode *> _nodes;

  // map hnl monitors (they are nodes) to (action, hnlmonitor) pairs
  std::map<SliceTreeNode *, std::map<ActionEventType, SliceTreeNode>> _edges;

public:
#include "create-hnl-monitor.h"
#include "hna-next-slice.h"
#include "slices-tree-ctor.h"

  SliceTreeNode &getRoot() { return root; };

  SliceTreeNode *getSuccessor(SliceTreeNode *node, const ActionEvent &ev) {
    auto it = _edges.find(node);
    if (it == _edges.end()) {
      return nullptr;
    }

    assert(ev.isAction());
    auto iit = it->second.find(ev.type);
    if (iit == it->second.end()) {
      return nullptr;
    }

    return &iit->second;
  }

  SliceTreeNode *addSlice(SliceTreeNode *node, const ActionEvent &ev) {
    assert(!getSuccessor(node, ev));
    assert(ev.isAction());
    auto next_node = nextSliceTreeNode(node->type, ev.type);
    if (next_node == HNANodeType::INVALID) {
      return nullptr;
    }

    auto &slice =
        _edges[node]
            .emplace(ev.type,
                     SliceTreeNode{createHNLMonitor(next_node), next_node})
            .first->second;
    // _monitors.push_back(slice.monitor.get());
    _nodes.push_back(&slice);

    return &slice;
  }

  // auto monitors_begin() -> auto { return _monitors.begin(); }
  // auto monitors_end() -> auto { return _monitors.end(); }

  auto begin() -> auto { return _nodes.begin(); }
  auto end() -> auto { return _nodes.end(); }
};

class HNAMonitor : public Monitor {
  SlicesTree _slices_tree;
  // Mapping of traces (their IDs) to slices they are currently in
  std::map<unsigned, SliceTreeNode *> _trace_to_slice;

  SliceTreeNode *getSlice(unsigned trace_id);
  SliceTreeNode *getOrCreateSlice(SliceTreeNode *current_node,
                                  unsigned trace_id, const ActionEvent &e);

  bool _traces_finished{false};
  // updating traces can yield a verdict (e.g., if there is no
  // matching action in the HNA). If that happens, it is stored here
  // and returned on the next call of `step`.
  Verdict _result{Verdict::UNKNOWN};

public:
  /*
   AtomMonitor *createAtomMonitor(Action monitor_type, HNLInstance&);
   void removeInstance(HNLInstance *instance);
   */

  // adding and extending traces
  void newTrace(unsigned id);
  void extendTrace(unsigned trace_id, const ActionEvent &e);
  void traceFinished(unsigned trace_id);
  void noFutureUpdates();

  Verdict step();

  // statistics
  struct {
    // number of HNL monitors
    size_t num_hnl_monitors{1};
  } stats;
};

#endif
