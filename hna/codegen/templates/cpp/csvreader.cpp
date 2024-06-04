#include <iostream>
#include <string>
#include <cstring>

#include "csvreader.h"

CSVEventsStream::CSVEventsStream(const std::string &file, unsigned trace_id)
    : Stream(trace_id), _stream(file) {
  _stream.open(file, std::ios_base::in);
  if (!_stream.is_open()) {
    std::cerr << "Failed opening file '" << file << "'\n";
    std::cerr << "  error: " << strerror(errno) << "'\n";
    abort();
  }
  _stream.clear();
}

CSVEventsStream::~CSVEventsStream() { _stream.close(); }

bool CSVEventsStream::finished() const { return _finished; }
