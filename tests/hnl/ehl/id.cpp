#include <map>
#include <memory>
#include <set>

#include "events.h"
#include "function-id.h"
#include "sharedtraceset.h"
#include "trace.h"

////
/// -------- Identity function ------------------------------------------
class FunctionId : public Function_id {
  std::map<Trace *, SharedTraceSet> _sets;
  std::map<Trace *, Trace *> _inout;

public:
  bool noFutureUpdates() const override { return _inout.empty(); }

  SharedTraceSet &getTraceSet(Trace *t1) override {
    auto &S = _sets[t1];
    if (S.hasTrace(t1->id()) == 0) {
      _inout[t1] = S.newTrace(t1->id());
    } // else: some atom already uses this set

    return S;
  }

  void step() override {
    for (auto it = _inout.begin(), et = _inout.end(); it != et;) {
      auto &[in, out] = *it;
      size_t n = out->size();
      Event ev;
      bool erase = false;
      while (true) {
        auto r = in->get(n, ev);
        if (r != TraceQuery::AVAILABLE) {
          if (r == TraceQuery::END) {
            // out->setFinished();
            _sets[in].traceFinished(in->id());
            _sets[in].noFutureUpdates();
            erase = true;
          }
          break;
        }
        // std::cerr << "COPY " << ev << "\n";
        out->append(ev);
        ++n;
      }
      if (erase) {
        auto tmp = it++;
        _inout.erase(tmp);
      } else {
        ++it;
      }
    }
  }
};

std::unique_ptr<Function> createFunction_id() {
  return std::unique_ptr<Function>{new FunctionId{}};
}
