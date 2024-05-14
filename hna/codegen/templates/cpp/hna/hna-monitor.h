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

    // map hnl monitors (they are nodes) to (action, hnlmonitor) pairs
    std::map<SliceTreeNode *, std::map<ActionEventType, SliceTreeNode>> _edges;

public:
    #include "slices-tree-ctor.h"

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

        return _edges[node].emplace(ev.type, nextSliceTreeNode(node->type, ev.type))->second;
    }


};

class HNAMonitor : public Monitor {
  bool _traces_finished{false};

  SlicesTree _slices_tree;
  // Mapping of traces (their IDs) to slices they are currently in
  std::map<unsigned, SliceTreeNode *> _trace_to_slice;

  SliceTreeNode *getSlice(unsigned trace_id);
  SliceTreeNode *getOrCreateSlice(SliceTreeNode *current_node, unsigned trace_id, const ActionEvent& e);

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
