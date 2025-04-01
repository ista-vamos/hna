#ifndef HNL_EVALUATION_STATE_H_
#define HNL_EVALUATION_STATE_H_

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


#endif // HNL_EVALUATION_STATE_H_
