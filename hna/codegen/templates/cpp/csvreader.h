#ifndef CSVREADER_H_
#define CSVREADER_H_

#include <atomic>
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
  using IDTy = unsigned;
  const IDTy _id;

public:
  Stream(IDTy trace_id) : _id(trace_id) {}

  IDTy id() const { return _id; }
  // Not implemented -- the child classes need to implement it
  // NOTE: these methods are not virtual intentionally,
  // they are here just to have the full interface for child classes,
  // but we do not plan to use this class to dispatch calls for subclasses.
  bool try_read(Event &ev);
  bool finished() const;
};


class CSVEventsStream : public Stream {
#ifdef USE_CSV_PARSER
  csv::CSVReader _reader;
#endif
  std::ifstream _stream;
  bool _finished{false};
  size_t _events_num_read{0};

public:
  CSVEventsStream(const std::string& file, unsigned trace_id);
  ~CSVEventsStream();

  // Try reading an event. Return `true` if the event was read
  // in which case the event was stored into `ev`.
  // Otherwise return `false`.
  bool try_read(Event &ev);
  // Return `true` if the stream finished.
  bool finished() const;
};


template <typename StreamTy, typename MonitorTy>
void read_csv(CmdArgs& args, MonitorTy& M, std::atomic<bool>& running) {
  std::cerr << "Reading CSV events\n";

  std::vector<std::unique_ptr<StreamTy>> streams;
  std::vector<std::unique_ptr<StreamTy>> tmp_streams;

  size_t num_open_files = 0;
  size_t next_input = 0;
  const size_t inputs_num = args.inputs.size();
  const size_t read_limit = args.read_max_num_events_at_once;

  while (running.load(std::memory_order_acquire)) {
    // check if we have new files to open
    if (next_input < inputs_num && num_open_files < args.open_traces_limit) {
        M.newTrace(next_input + 1);
        streams.emplace_back(std::make_unique<StreamTy>(args.inputs[next_input], next_input + 1));
        ++next_input;
    }

    // check if we can read from some of those files
    Event ev;
    bool removed = false;
    for (size_t i = 0; i < streams.size(); ++i) {
      auto *stream = streams[i].get();

      if (stream->try_read(ev)) {
        M.extendTrace(stream->id(), ev);
      } else {
        if (stream->finished()) {
          M.traceFinished(stream->id());
          streams[i].reset();
          removed = true;
        }
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
      M.tracesFinished();
      break;
    }
  }
}


#endif

