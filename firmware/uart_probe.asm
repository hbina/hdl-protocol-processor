# UART exploration image, 115200 baud (434 core clocks/bit at 50 MHz).
# uio0=TX, uio1=RX. Valid requests only; NOT the final UART runtime ABI.
# Host supplies 0..64 TX bytes, parameter[0]=0..64 RX count, enough output room.
# Consumes the full submission, echoes ID, publishes standard terminal event.
# r3=0xa5 throughout RX. A finite 65536-poll budget restarts per received byte.
# Scratch: event 144..159, remaining receive count 160.
    SETO 1
    SETOE 1
idle:
    LDI r3, 0x22
    PREAD r0, r3
    JFAIL idle
    LDI r1, 144
    STORE r0, r1
    PREAD r0, r3
    ADDI r1, 1
    STORE r0, r1
    LDI r2, 14
record:
    PREAD r0, r3
    DJNZ r2, record
    LDI r1, 146
    LDI r0, 1
    STORE r0, r1
    ADDI r1, 1
    LDI r2, 13
    LDI r0, 0
clear_event:
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, clear_event
    LDI r3, 2
    PREAD r1, r3
    LDI r2, 148
    STORE r1, r2
    LDI r3, 0x11
    JZ r1, receive
tx_byte:
    PREAD r0, r3
    LDI r2, 0
    OUTBIT r2, 0
    LDI r2, 8
    WAIT 255
    WAIT 175
tx_bit:
    OUTBIT r0, 0
    SHR r0
    WAIT 255
    WAIT 174
    DJNZ r2, tx_bit
    SETO 1
    WAIT 255
    WAIT 176
    DJNZ r1, tx_byte
receive:
    LDI r1, 0
    LOAD r0, r1
    LDI r1, 160
    STORE r0, r1
    JZ r0, publish
    LDI r3, 0xa5
rx_byte:
    LDI r1, 0
    LDI r2, 0
search:
    IN r0
    ANDI r0, 2
    JZ r0, candidate
count_poll:
    DJNZ r1, search
    DJNZ r2, search
    LDI r2, 6
    JMP fail
candidate:
    WAIT 210
    IN r0
    ANDI r0, 2
    JZ r0, qualified
    JMP count_poll
qualified:
    LDI r0, 0
    LDI r1, 8
    WAIT 255
    WAIT 173
rx_bit:
    INBIT r0, 1
    ROR r0
    WAIT 255
    WAIT 174
    DJNZ r1, rx_bit
    IN r1
    ANDI r1, 2
    JZ r1, framing
    LDI r1, 0x30
    PWRITE r0, r1
    LDI r0, 0
    ADDI r1, 1
    PWRITE r0, r1
    ADDI r1, 1
    PWRITE r0, r1
    LDI r1, 150
    LOAD r0, r1
    ADDI r0, 1
    STORE r0, r1
    LDI r1, 160
    LOAD r0, r1
    ADDI r0, 255
    STORE r0, r1
    JZ r0, publish
    JMP rx_byte
framing:
    LDI r2, 7
fail:
    LDI r1, 147
    STORE r2, r1
publish:
    LDI r3, 0
    LDI r1, 144
    LDI r2, 16
    LDI r3, 0x40
event:
    LOAD r0, r1
    PWRITE r0, r3
    ADDI r1, 1
    DJNZ r2, event
    LDI r0, 0
    ADDI r3, 1
    PWRITE r0, r3
    JMP idle
