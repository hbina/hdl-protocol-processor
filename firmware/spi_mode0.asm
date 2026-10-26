# One SPI mode-0 transfer of 0xA5, MSB first.
# Pin 1: SCLK (push-pull)
# Pin 2: MOSI (push-pull)
# Pin 3: MISO (input)
# Received byte is stored in RAM[0] and published on output bank 1.

    LDI    r0, 0xA5       # transmit register
    LDI    r1, 0x00       # receive register
    LDI    r2, 8          # bit count
    LDI    r3, 0x00
    OUT    r3, 0
    LDI    r3, 0x06
    OE     r3, 0           # SCLK and MOSI are outputs

bit_loop:
    ROL    r0             # original MSB moves to bit zero
    OUTBIT r0, 2          # present MOSI while SCLK is low
    WAIT   4

    LDI    r3, 1
    OUTBIT r3, 1          # rising edge: peer samples MOSI
    WAIT   4

    SHL    r1
    INBIT  r3, 3
    OR     r1, r3          # sample synchronized MISO

    LDI    r3, 0
    OUTBIT r3, 1          # falling edge
    WAIT   4
    DJNZ   r2, bit_loop

    LDI    r0, 0
    STORE  r1, r0
    OUT    r1, 1
    HALT
