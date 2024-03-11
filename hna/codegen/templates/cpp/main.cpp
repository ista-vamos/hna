#include <cassert>
#include <iostream>

#include "monitor.h"
#include "inputs.h"

int monitor(Inputs &inputs);

int main() {
  Inputs inputs;
  return monitor(inputs);
}
