#ifndef CSVREADER_H_
#define CSVREADER_H_

#include <atomic>
#include <cassert>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <string>
#include <vector>

#include "cmd.h"
#include "csvreader-aux.h"
#include "events.h"
#include "stream.h"

class CSVEventsStream : public Stream {
#ifdef USE_CSV_PARSER
  csv::CSVReader _reader;
#endif
  std::ifstream _stream;
  bool _finished{false};
  size_t _events_num_read{0};

public:
  CSVEventsStream(const std::string &file, unsigned trace_id);
  ~CSVEventsStream();

  // Try reading an event. Return `true` if the event was read
  // in which case the event was stored into `ev`.
  // Otherwise return `false`.
  template <typename EventTy> bool try_read(EventTy &ev) {
    assert(!finished() && "Reading finished file");

    assert(!_stream.bad());
    _stream >> std::ws;
    if (_stream.eof()) {
      _finished = true;
      return false;
    }

    // generated part follows
#include "read_csv_event.h"

    ++_events_num_read;

    // std::cout << "[" << id() << "] IN: " << ev << "\n";
    return true;
  }
  // Return `true` if the stream finished.
  bool finished() const;
};

template <typename StreamTy, typename MonitorTy, typename EventTy = Event>
void read_csv(CmdArgs &args, MonitorTy &M, std::atomic<bool> &running) {
  std::cerr << "Reading CSV events\n";

  std::vector<std::unique_ptr<StreamTy>> streams;
  std::vector<std::unique_ptr<StreamTy>> tmp_streams;

  size_t num_open_files = 0;
  size_t next_input = 0;
  const size_t inputs_num = args.inputs.size();
  // const size_t read_limit = args.read_max_num_events_at_once;

  while (running.load(std::memory_order_acquire)) {
    // check if we have new files to open
    if (next_input < inputs_num && num_open_files < args.open_traces_limit) {
      M.newTrace(next_input + 1);
      streams.emplace_back(
          std::make_unique<StreamTy>(args.inputs[next_input], next_input + 1));
      ++next_input;
      ++num_open_files;
    }

    // check if we can read from some of those files
    EventTy ev;
    bool removed = false;
    for (size_t i = 0; i < streams.size(); ++i) {
      auto *stream = streams[i].get();

      if (stream->template try_read<EventTy>(ev)) {
        M.extendTrace(stream->id(), ev);
      } else {
        if (stream->finished()) {
          M.traceFinished(stream->id());
          streams[i].reset();
          removed = true;
      	  --num_open_files;
        }
      }
    }

    // FIXME: do this more efficiently
    if (removed) {
      tmp_streams.reserve(streams.size() - 1);
      for (auto &stream : streams) {
        if (stream) {
          tmp_streams.push_back(std::move(stream));
	}
      }
      streams.swap(tmp_streams);
      tmp_streams.clear();
    }

    if (streams.empty()) {
      M.noFutureUpdates();
      break;
    }
  }
}

#endif
