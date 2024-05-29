#include <map>
#include <memory>
#include <set>

#include "events.h"
#include "sharedtraceset.h"
#include "traceset.h"
#include "trace.h"
#include "csvreader.h"
#include "cmd.h"

#include "function-samples.h"

bool inputsArePrefixes(Trace *t1, Trace *t2) {
    assert(t1->finished());
    assert(t2->finished());
    Event ev1, ev2;
    size_t n = t1->size();
    size_t m = t2->size();
    if (n > m)
        return false;

    for (size_t i = 0; i < n; ++i) {
        auto r = t1->get(i, ev1);
        assert (r != TraceQuery::END);
        r = t2->get(i, ev2);
        assert (r != TraceQuery::END);

        if (ev1.in != ev2.in) {
            return false;
        }
    }

    auto r = t1->get(n, ev1);
    assert (r == TraceQuery::END);

    return true;
}

////
/// -------- Sampling function ------------------------------------------
class FunctionSamples : public Function_samples {
  std::map<Trace *, SharedTraceSet> _shared_sets;
  std::set<Trace *> _done_traces;

  CmdArgs *_cmd;
  TraceSet traces;
  size_t num_traces;

public:
  FunctionSamples(CmdArgs *cmd) : _cmd(cmd) {
      // read all CSV files
      // FIXME: or a subset
      std::atomic<bool> running{true};
      read_csv<CSVEventsStream, TraceSet>(*cmd, traces, running);

      while(traces.getNewTrace())
          ;

      num_traces = traces.size();
  }

  bool noFutureUpdates() const override { return _done_traces.size() == num_traces; }

  SharedTraceSet &getTraceSet(Trace *t) override {
    auto &SS = _shared_sets[t];
    return SS;
  }

  void step() override {

      for (auto& [trace, SS] : _shared_sets) {
          if (!trace->finished())
              continue;

          if (!_done_traces.insert(trace).second)
              continue;

          // divide the traces by the inputs
          for (auto& [t_id, t_ptr] : traces) {
              if (inputsArePrefixes(trace, t_ptr.get())) {
                  auto *new_t = SS.newTrace(t_id);
                  t_ptr->copyTo(new_t);
                  assert(new_t->finished());
              } else {
                  // sanity check
                  assert(trace != t_ptr.get());
              }
          }
      }
  }
};

std::unique_ptr<Function> createFunction_samples(CmdArgs *cmd) {
  return std::unique_ptr<Function>{new FunctionSamples{cmd}};
}
