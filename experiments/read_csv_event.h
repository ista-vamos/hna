uint64_t *num = &ev.in;
*num = 0;
bool in_num = false;
unsigned n = 0;
char buff[64] = {0};
char c;
#ifndef NDEBUG
bool saw_semicolon = false;
#endif

while ((_stream.get(c))) {
    if (std::isdigit(c)) {
        if (!in_num) {
            // START
            n = 0;
        }
        in_num = true;
        buff[n++] = c;
    } else {
        if (in_num) {
            // END

            // convert the string that holds the current number of the bit
            // into an unsigned number
            unsigned pow = 1;
            unsigned N = 0;
            while (n-- > 0) {
                N += (buff[n] - '0') * pow;
                pow *= 10;
            }
            assert(N < 64 && "Our variables are at most 64-bit");
            // set the Nth bit to true in the number
            *num |= 1UL << N;
        }
        in_num = false;
    }

    if (c == '\n') {
        break;
    }
    if (c == ';') {
#ifndef NDEBUG
	saw_semicolon = true;
#endif
        num = &ev.out;
        *num = 0;
    }
}

assert(saw_semicolon && "The line had no semicolon");


