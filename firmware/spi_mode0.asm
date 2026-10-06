# One SPI mode-0 transfer of 0xA5, MSB first.
# Pin 1: SCLK (push-pull)
# Pin 2: MOSI (push-pull)
# Pin 3: MISO (input)
# Received data remains in r1 and is visible by setting ui_in[1:0] = 1.

    LDI    r0, 0xA5       # transmit register
    LDI    r1, 0x00       # receive register
    LDI    r2, 8          # bit count
    SETO   0x00
    SETOE  0x06           # SCLK and MOSI are outputs

bit_loop:
    ROL    r0             # original MSB moves to bit zero
    OUTBIT r0, 2          # present MOSI while SCLK is low
    WAIT   4

    LDI    r3, 1
    OUTBIT r3, 1          # rising edge: peer samples MOSI
    WAIT   4

    SHL    r1
    INBIT  r1, 3          # sample synchronized MISO

    LDI    r3, 0
    OUTBIT r3, 1          # falling edge
    WAIT   4
    DJNZ   r2, bit_loop

    HALT
