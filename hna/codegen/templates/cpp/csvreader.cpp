#include <iostream>

#include "csvreader.h"
#include "trace.h"

CSVEventsStream::CSVEventsStream(const std::string& file, Trace *t) : Stream(t) {
    _stream.open(file, std::fstream::in);
    if (!_stream.is_open()) {
        std::cerr << "Failed opening `" << file << "`\n";
        abort();
    }
}

CSVEventsStream::~CSVEventsStream() {
  if (_stream.is_open())
    _stream.close();
}

void CSVEventsStream::try_read(size_t limit) {
  if (_stream.eof()) {
    trace->setFinished();
  }

}

bool CSVEventsStream::finished() const {
  return _stream.eof();
}

