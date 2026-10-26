# Transmit 0xA5 as 8N1 UART at 1 Mbaud with a 50 MHz system clock.
# Pin 0: TX (push-pull)

    LDI    r0, 0xA5       # transmit shift register
    LDI    r1, 0x00       # constant zero / start bit
    LDI    r2, 8          # data-bit count
    LDI    r3, 0x01       # constant one / stop bit

    LDI    r3, 0x01
    OE     r3, 0           # pin 0 is an output
    LDI    r3, 0x01
    OUT    r3, 0           # idle high
    WAIT   8              # visible idle interval

    OUTBIT r1, 0          # start bit
    WAIT   48             # start-to-data spacing = 50 clocks

data_bit:
    OUTBIT r0, 0          # transmit least-significant bit
    WAIT   46             # includes SHR and DJNZ overhead
    SHR    r0
    DJNZ   r2, data_bit

    OUTBIT r3, 0          # stop bit
    WAIT   48
    HALT
