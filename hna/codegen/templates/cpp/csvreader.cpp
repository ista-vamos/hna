#include <iostream>

#include "csvreader.h"
#include "trace.h"
#include "csv.hpp"

CSVEventsStream::CSVEventsStream(const std::string& file, Trace *t)
    : Stream(t), _reader(file) {
/*
    _stream.open(file, std::fstream::in);
    if (!_stream.is_open()) {
        std::cerr << "Failed opening `" << file << "`\n";
        abort();
    } else {
        std::cerr << "Opened file: " << file  << "\n";
    }
*/
}

CSVEventsStream::~CSVEventsStream() {
 //if (_stream.is_open())
 //  _stream.close();
}

void CSVEventsStream::try_read(size_t limit) {
  assert(!finished() && "Reading finished file");

  csv::CSVRow row;
  if (!_reader.read_row(row)) {
    _finished = true;
    trace->setFinished();
    return;
  }

  ++_events_num_read;

  Event ev;

  // generated part follows
  #include "try_read_csv_event.cpp"
  //std::cout << "IN: " << ev << "\n";

  trace->append(ev);
}

bool CSVEventsStream::finished() const {
  return _finished;
}
