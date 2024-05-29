#include <map>
#include <memory>
#include <set>
#include <algorithm>

#include "events.h"
#include "sharedtraceset.h"
#include "traceset.h"
#include "trace.h"
#include "csvreader.h"
#include "cmd.h"

#include "hnl-0/function-testP.h"


//using namespace hnl_0;
////
/// -------- Sampling function ------------------------------------------
class FunctionTest : public Function_testP {
  std::map<Trace *, SharedTraceSet> _shared_sets;
  std::set<Trace *> _done_traces;

  CmdArgs *_cmd;
  size_t _trace_id{0};

public:
  FunctionTest(CmdArgs *cmd) : _cmd(cmd) { }

  bool noFutureUpdates() const override { return _done_traces.size() == _shared_sets.size(); }

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
          
          auto n = trace->size();
          for (int i = 0; i < n; ++i) {
            auto *new_t = SS.newTrace(++_trace_id);
            trace->copyTo(new_t);
            std::random_shuffle(new_t->events().begin(), new_t->events().end());
          }
      }
  }
};

std::unique_ptr<Function> createFunction_testP(CmdArgs *cmd) {
  return std::unique_ptr<Function>{new FunctionTest{cmd}};
}
