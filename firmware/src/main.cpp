// KeySmith firmware
// ==================
//
// A USB HID keyboard relay. Listens on USB CDC serial for a tiny binary
// protocol and emits real HID keystrokes via NicoHood/HID-Project.
//
// Wire protocol (all integers are single bytes unless noted):
//
//   [0xA5][0x01][hid_code]   PRESS       press the given HID usage code
//   [0xA5][0x02][hid_code]   RELEASE     release the given HID usage code
//   [0xA5][0x03]             RELEASE_ALL release every key (panic / safety)
//   [0xA5][0x04]             PING        board replies [0x5A][version]
//
// Design notes:
//   * 0xA5 is the magic / sync byte. Anything not preceded by 0xA5 is
//     ignored. This gives us a self-resyncing stream — line noise or a
//     stale write from the host can't accidentally inject keys.
//   * If a multi-byte command doesn't complete within FRAME_TIMEOUT_MS,
//     the parser resets. Prevents a half-sent command from latching the
//     state machine.
//   * On boot we release_all() before attaching HID, so a power glitch
//     during a previous press can't leave a key stuck.
//   * Errors are silently dropped. The host uses PING to detect liveness.
//
// HID codes are USB HID Usage IDs from the Keyboard/Keypad Page (0x07).
// E.g. International3 = 0x87. See HID-Project's KeyboardLayout.h.

#include <Arduino.h>
#include <HID-Project.h>

#ifndef KEYSMITH_PROTOCOL_VERSION
#define KEYSMITH_PROTOCOL_VERSION 1
#endif

// ---- Protocol constants ---------------------------------------------------

static constexpr uint8_t MAGIC          = 0xA5;
static constexpr uint8_t REPLY_MAGIC    = 0x5A;

static constexpr uint8_t OP_PRESS       = 0x01;
static constexpr uint8_t OP_RELEASE     = 0x02;
static constexpr uint8_t OP_RELEASE_ALL = 0x03;
static constexpr uint8_t OP_PING        = 0x04;

static constexpr unsigned long FRAME_TIMEOUT_MS = 200;

// ---- Parser state ---------------------------------------------------------

enum class ParseState : uint8_t {
    WAIT_MAGIC,
    WAIT_OP,
    WAIT_ARG,
};

static ParseState  state          = ParseState::WAIT_MAGIC;
static uint8_t     pendingOp      = 0;
static unsigned long frameStarted = 0;

// ---- Helpers --------------------------------------------------------------

static void resetParser() {
    state = ParseState::WAIT_MAGIC;
    pendingOp = 0;
    frameStarted = 0;
}

static void doPress(uint8_t hidCode) {
    // BootKeyboard accepts raw HID usage codes via KeyboardKeycode cast.
    BootKeyboard.press(static_cast<KeyboardKeycode>(hidCode));
}

static void doRelease(uint8_t hidCode) {
    BootKeyboard.release(static_cast<KeyboardKeycode>(hidCode));
}

static void doReleaseAll() {
    BootKeyboard.releaseAll();
}

static void doPing() {
    Serial.write(REPLY_MAGIC);
    Serial.write(static_cast<uint8_t>(KEYSMITH_PROTOCOL_VERSION));
}

// ---- Arduino entry points -------------------------------------------------

void setup() {
    Serial.begin(115200);

    // BootKeyboard gives us a standard HID keyboard descriptor that macOS
    // recognises immediately and lets Karabiner-Elements treat us as a
    // normal keyboard device.
    BootKeyboard.begin();

    // Defensive: in case anything was held when we lost power.
    doReleaseAll();
}

void loop() {
    // Timeout half-received frames so a dropped byte can't wedge us.
    if (state != ParseState::WAIT_MAGIC &&
        (millis() - frameStarted) > FRAME_TIMEOUT_MS) {
        resetParser();
    }

    while (Serial.available() > 0) {
        const uint8_t b = static_cast<uint8_t>(Serial.read());

        switch (state) {
            case ParseState::WAIT_MAGIC:
                if (b == MAGIC) {
                    state = ParseState::WAIT_OP;
                    frameStarted = millis();
                }
                // else: silently discard junk
                break;

            case ParseState::WAIT_OP:
                pendingOp = b;
                switch (b) {
                    case OP_PRESS:
                    case OP_RELEASE:
                        state = ParseState::WAIT_ARG;
                        break;

                    case OP_RELEASE_ALL:
                        doReleaseAll();
                        resetParser();
                        break;

                    case OP_PING:
                        doPing();
                        resetParser();
                        break;

                    default:
                        // Unknown opcode — drop frame.
                        resetParser();
                        break;
                }
                break;

            case ParseState::WAIT_ARG:
                if (pendingOp == OP_PRESS) {
                    doPress(b);
                } else if (pendingOp == OP_RELEASE) {
                    doRelease(b);
                }
                resetParser();
                break;
        }
    }
}
