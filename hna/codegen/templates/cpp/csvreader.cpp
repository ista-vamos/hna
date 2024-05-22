#include <iostream>
#include <string>

#include "csvreader.h"

CSVEventsStream::CSVEventsStream(const std::string &file, unsigned trace_id)
    : Stream(trace_id), _stream(file) {
  _stream.open(file);
  if (!_stream.is_open()) {
    std::cerr << "Failed opening file '" << file << "'\n";
    abort();
  }
}

CSVEventsStream::~CSVEventsStream() { _stream.close(); }

bool CSVEventsStream::finished() const { return _finished; }
