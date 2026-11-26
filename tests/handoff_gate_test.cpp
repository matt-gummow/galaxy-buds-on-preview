#include "BudsOnHandoffGate.h"

#include <cstdio>
#include <cstdlib>
#include <limits>

static void expect(bool condition, const char *description) {
    if (!condition) {
        std::fprintf(stderr, "%s\n", description);
        std::exit(1);
    }
}

int main() {
    // Independent reference used by the offline Galaxy Book trace classifier.
    // CRC-16/XMODEM of the three body bytes is 0x1c79, stored little endian.
    const std::array<uint8_t, 9> expected{0xfc, 0x05, 0x00, 0x01, 0x71, 0x01, 0x79, 0x1c, 0xcc};
    expect(MakeBudsOnHandoffFrame() == expected, "wrong SMEP frame, flags, body, length, CRC or trailer");

    BudsOnHandoffGate gate;
    expect(gate.consume(0, 9000) == 4, "zero ticket accepted");
    expect(gate.consume(11, 9000) == 4, "request accepted without preparation");
    gate.arm(11, 500);
    expect(gate.consume(11, 500) == 6, "request accepted during preparation");
    expect(gate.consume(11, 3499) == 6, "request accepted before baseline elapsed");
    expect(gate.consume(12, 3500) == 4, "wrong ticket accepted");
    expect(gate.consume(11, 3500) == 0, "valid request at 3s rejected");
    expect(gate.consume(11, 3500) == 4, "ticket reused after send attempt");

    gate.arm(13, 10000);
    gate.arm(14, 11000);
    expect(gate.consume(13, 14999) == 4, "replacement left old ticket armed");
    expect(gate.consume(14, 70999) == 0, "valid request just before expiry rejected");
    gate.arm(15, 10000);
    expect(gate.consume(15, 70000) == 4, "ticket survived its 60s deadline");
    expect(gate.consume(15, 20000) == 4, "expired ticket revived");

    gate.arm(16, 10000);
    gate = {};
    expect(gate.consume(16, 14000) == 4, "cancelled ticket accepted");
    gate.arm(17, 10000);
    gate.arm(0, 11000);
    expect(gate.consume(17, 14000) == 4, "zero arm retained a grant");
    expect(gate.consume(0, 14000) == 4, "zero arm issued a grant");

    // Time comparisons must fail closed if the clock ever regresses or wraps.
    gate.arm(18, std::numeric_limits<uint64_t>::max() - 10);
    expect(gate.consume(18, 3001) == 4, "clock rollback retained a grant");
    return 0;
}
