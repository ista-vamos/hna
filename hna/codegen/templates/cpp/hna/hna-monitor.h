#ifndef HNA_MONITOR_H_
#define HNA_MONITOR_H_

#include <vector>
#include <list>
#include <memory>

#include "trace.h"
#include "traceset.h"
#include "verdict.h"
#include "monitor.h"

// generated
#include "events.h"
#include "hnl-monitors.h"
#include "hna_node_types.h"

struct SliceTreeNode {
    std::unique_ptr<Monitor> monitor;
    HNANodeType type;

    SliceTreeNode(Monitor *m, HNANodeType ty) : monitor(m), type(ty) {}

    void newTrace(unsigned trace_id) {
        #include "dispatch-new-trace.h"
    }

    void traceFinished(unsigned trace_id) {
        #include "dispatch-trace-finished.h"
    }

    void extendTrace(unsigned trace_id, const Event& ev) {
        #include "dispatch-extend-trace.h"
    }

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
    #include "slices-tree-ctor.h"
    #include "hna-next-slice.h"
    #include "create-hnl-monitor.h"

    SliceTreeNode &getRoot() { return root; };

    SliceTreeNode *getSuccessor(SliceTreeNode *node, const ActionEvent& ev) {
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

    SliceTreeNode *addSlice(SliceTreeNode *node, const ActionEvent& ev) {
        assert(!getSuccessor(node, ev));
        assert(ev.isAction());
        auto next_node = nextSliceTreeNode(node->type, ev.type);
        if (next_node == HNANodeType::INVALID) {
          return nullptr;
        }

        auto &slice = _edges[node].emplace(ev.type, SliceTreeNode{createHNLMonitor(next_node), next_node}).first->second;
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
  SliceTreeNode *getOrCreateSlice(SliceTreeNode *current_node, unsigned trace_id, const ActionEvent& e);

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
  void tracesFinished();

  Verdict step();

  // statistics
  struct {
    // number of HNL monitors
    size_t num_hnl_monitors{1};
  } stats;
};


#endif
