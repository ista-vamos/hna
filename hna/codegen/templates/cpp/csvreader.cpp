#include <iostream>
#include <string>
#include <limits>

#include "csvreader.h"
#include "trace.h"


CSVEventsStream::CSVEventsStream(const std::string& file, unsigned trace_id)
    : Stream(trace_id), _stream(file) {
    _stream.open(file);
    if (!_stream.is_open()) {
        std::cerr << "Failed opening file '" << file << "'\n";
        abort();
    }
}

CSVEventsStream::~CSVEventsStream() {
    _stream.close();
}

bool CSVEventsStream::try_read(Event &ev) {
  assert(!finished() && "Reading finished file");

  _stream >> std::ws;
  if (_stream.eof()) {
      _finished = true;
      return false;
  }

   // generated part follows
  #include "read_csv_event.cpp"

  ++_events_num_read;

  std::cout << "[" << id() << "] IN: " << ev << "\n";
  return true;
}


bool CSVEventsStream::finished() const {
  return _finished;
}

#ifdef USE_CSV_PARSER
#include "csv.hpp"

namespace csv_parser {
// This implementation uses the csv-parser project,
// for for parsing the actions, we might want to modify it,
// so we added a different implementation lower

CSVEventsStream::CSVEventsStream(const std::string& file, unsigned trace_id)
    : Stream(trace_id), _reader(file) {
}


bool CSVEventsStream::try_read(Event &ev) {
  assert(!finished() && "Reading finished file");

  csv::CSVRow row;
  if (!_reader.read_row(row)) {
    _finished = true;
    return false;
  }

  ++_events_num_read;

  // generated part follows
  #include "try_read_csv_event.cpp"

  std::cout << "[" << id() << "] IN: " << ev << "\n";
  return true;
}


bool CSVEventsStream::finished() const {
  return _finished;
}

} // namespace csv_parser


CSVEventsStream::CSVEventsStream(const std::string& file, unsigned trace_id)
    : Stream(trace_id), _reader(file) {
}
#endif
