# Emit an I2C START and write address byte 0xA0, then sample ACK/NACK.
# Pin 4: SCL (open-drain; external pull-up required)
# Pin 5: SDA (open-drain; external pull-up required)
# r3 bit zero contains the sampled ACK value: 0=ACK, 1=NACK.

    SETO   0x00           # open-drain pins always drive zero
    SETOE  0x00           # release both bus lines
    LDI    r0, 0xA0       # address byte
    LDI    r1, 8          # bit count
    LDI    r2, 1          # drive-enable constant
    LDI    r3, 0          # ACK result
    WAIT   8

    OEBIT  r2, 5          # START: SDA low while SCL is released
    WAIT   4
    OEBIT  r2, 4          # pull SCL low

bit_loop:
    ROL    r0             # original MSB moves to bit zero
    OEBITN r0, 5          # data 1 releases SDA; data 0 drives it low
    WAIT   4

    LDI    r2, 0
    OEBIT  r2, 4          # release SCL high
    WAITPIN 4, 1          # support target clock stretching
    WAIT   4

    LDI    r2, 1
    OEBIT  r2, 4          # finish the clock pulse low
    WAIT   4
    DJNZ   r1, bit_loop

    LDI    r2, 0
    OEBIT  r2, 5          # release SDA for the ACK bit
    WAIT   4
    OEBIT  r2, 4          # release SCL high
    WAITPIN 4, 1
    WAIT   4
    INBIT  r3, 5          # sample ACK/NACK

    LDI    r2, 1
    OEBIT  r2, 4          # return SCL low
    HALT
