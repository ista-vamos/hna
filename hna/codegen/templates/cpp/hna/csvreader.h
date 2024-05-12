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
#include "csv.hpp"


class Stream {
protected:
  Trace *trace;
public:
  Stream(Trace *t) : trace(t) {}

  void try_read(size_t limit=~static_cast<size_t>(0));
  bool finished() const;
};


class CSVEventsStream : public Stream {
  csv::CSVReader _reader;
  bool _finished{false};
  size_t _events_num_read{0};

public:
  CSVEventsStream(const std::string& file, Trace *t);
  ~CSVEventsStream();

  void try_read(size_t limit=~static_cast<size_t>(0));
  bool finished() const;
};


template <typename StreamTy>
void read_csv(CmdArgs& args, TraceSet& traces, std::atomic<bool>& running) {
  std::cerr << "Reading CSV events\n";

  std::vector<std::unique_ptr<StreamTy>> streams;
  std::vector<std::unique_ptr<StreamTy>> tmp_streams;

  size_t num_open_files = 0;
  size_t next_input = 0;
  const size_t inputs_num = args.inputs.size();
  const size_t read_limit = args.read_max_num_events_at_once;

  while (running) {
    // check if we have new files to open
    if (next_input < inputs_num && num_open_files < args.open_traces_limit) {
        auto *trace = traces.newTrace();
        streams.push_back(std::make_unique<StreamTy>(args.inputs[next_input++], trace));
    }

    // check if we can read from some of those files
    bool removed = false;
    for (size_t i = 0; i < streams.size(); ++i) {
      auto *stream = streams[i].get();

      stream->try_read(read_limit);
      if (stream->finished()) {
        streams[i].reset();
        removed = true;
      }
    }

    if (removed) {
      tmp_streams.reserve(streams.size() - 1);
      for (auto& stream : streams) {
        if (stream)
          tmp_streams.push_back(std::move(stream));
      }
      streams.swap(tmp_streams);
      tmp_streams.clear();
    }

    if (streams.empty()) {
      traces.setFinished();
      break;
    }
  }
}
#endif

