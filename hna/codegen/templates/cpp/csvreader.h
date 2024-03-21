#ifndef CSVREADER_H_
#define CSVREADER_H_

#include <vector>
#include <iostream>
#include <string>
#include <memory>
#include <fstream>

#include "cmd.h"
#include "traceset.h"
#include "trace.h"


class Stream {
protected:
  Trace *trace;
public:
  Stream(Trace *t) : trace(t) {}

  void try_read(size_t limit=~static_cast<size_t>(0));
  bool finished() const;
};


class CSVEventsStream : public Stream {
  std::fstream _stream;

public:
  CSVEventsStream(const std::string& file, Trace *t);
  ~CSVEventsStream();

  void try_read(size_t limit=~static_cast<size_t>(0));
  bool finished() const;
};


template <typename StreamTy>
void read_csv(CmdArgs& args, TraceSet& traces) {
  std::cerr << "Reading CSV events\n";

  std::vector<std::unique_ptr<StreamTy>> streams;

  // TODO: use FD polling in the future

  size_t num_open_files = 0;
  size_t next_input = 0;
  const size_t inputs_num = args.inputs.size();
  const size_t read_limit = args.read_max_num_events_at_once;

  while (next_input < inputs_num) {
    // check if we have some new files to open
    if (num_open_files < args.open_traces_limit) {
      auto *trace = traces.newTrace();
      streams.push_back(std::make_unique<StreamTy>(args.inputs[next_input++], trace));
    }

    // check if we can read from some of those files
    for (auto& stream : streams) {
      stream->try_read(read_limit);
      if (stream->finished()) {
        // TODO: remove stream
        // TODO: rotate vector
      }
    }
  }
}
#endif

