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
    // Independent reference used by the Galaxy Book trace classifier.
    auto expected = std::array<uint8_t, 18>{
        0xfc, 0x0e, 0x00, 0x01, 0x43, 0x04, 0x03, 0x07, 0x00,
        0x00, 0x0b, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0xcc
    };
    uint16_t crc = 0;
    for (size_t i = 3; i < expected.size() - 3; ++i) {
        crc ^= static_cast<uint16_t>(expected[i]) << 8;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = static_cast<uint16_t>((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
    }
    expected[15] = static_cast<uint8_t>(crc);
    expected[16] = static_cast<uint8_t>(crc >> 8);
    expect(BudsOnHostSetupFrame == expected, "wrong SMEP frame, flags, body, length, CRC or trailer");

    BudsOnHandoffGate gate;
    expect(gate.consume(0, 9000) == 4, "zero ticket accepted");
    expect(gate.consume(11, 9000) == 4, "request accepted without preparation");
    gate.arm(11, 500);
    expect(gate.consume(12, 500) == 4, "wrong ticket accepted");
    expect(gate.consume(11, 500) == 0, "confirmed request rejected after preparation");
    expect(gate.consume(11, 500) == 4, "ticket reused after send attempt");

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
