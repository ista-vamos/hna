#include <string>
#include <vector>

/***
* Class to parse command-line arguments
*/
class CmdArgs {
  int argc;
  char **argv;

  std::vector<std::string> inputs;


public:
  CmdArgs(int argc, char *argv[]) : argc(argc), argv(argv) {}

  bool csv_reader{false};
  bool trace_are_events{false};
  bool trace_are_aps{false};
  bool trace_is_signal{false};

  bool parse();
  void help() const;
};


