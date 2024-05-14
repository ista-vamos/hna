#include <iostream>

#include "csvreader.h"
#include "trace.h"
#include "csv.hpp"

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

