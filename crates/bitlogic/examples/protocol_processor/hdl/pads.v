// Example logical pad integration. Replace with target-specific IO cells and
// synchronization in the user's top module. No pull-ups are inferred here.
module protocol_pads(
    input wire [7:0] values, enables,
    inout wire [7:0] pads,
    output wire [7:0] inputs
);
    genvar pin;
    generate for(pin=0; pin<8; pin=pin+1) begin: pad
        assign pads[pin] = enables[pin] ? values[pin] : 1'bz;
    end endgenerate
    assign inputs = pads;
endmodule
