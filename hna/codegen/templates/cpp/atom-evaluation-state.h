#ifndef HNL_ATOM_EVALUATION_STATE_H_
#define HNL_ATOM_EVALUATION_STATE_H_

#include <vector>

using State = int;

struct EvaluationState {
  State state;

  // position in the traces
  unsigned p1{0};
  unsigned p2{0};

  EvaluationState(State s, unsigned p1, unsigned p2)
      : state(s), p1(p1), p2(p2) {}
};

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

  void new_to_this() {
    insert(begin(), _new_cfgs.begin(), _new_cfgs.end());
    _new_cfgs.clear();
  }

  void rotate() {
    clear();
    new_to_this();
  }
};

#endif // HNL_ATOM_EVALUATION_STATE_H_
