# Continuous copy: input 8 (ui[0]) -> output 8 (uo[0]).
# Inputs are synchronized; each loop takes three clocks after synchronization.
loop:
    INBIT r0, 8
    OUTBIT r0, 8
    JMP loop
