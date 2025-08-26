#ifndef EHL_EVALUATION_STATE_SET
#define EHL_EVALUATION_STATE_SET

#include "events.h"
#include "evaluation-state.h"

{{cg.namespace_start()}}

/**
 * This is a vector where new elements are pushed into a separate
 * storage and are moved to the main storage only on an explicit call.
 * This is because we iterate over the vector when adding.
 */
class EvaluationStateSet : public std::vector<EvaluationState> {
  std::vector<EvaluationState> _new_cfgs;

public:
  void emplace_new(State s, unsigned p1, unsigned p2) {
    _new_cfgs.emplace_back(s, p1, p2);
  }

  auto back_new() -> auto { return _new_cfgs.back(); }

  template <typename Arg> void push_new(Arg a) { _new_cfgs.push_back(a); }

  void rotate() {
    this->swap(_new_cfgs);
    _new_cfgs.clear();
  }
};

{{cg.namespace_end()}}

#endif