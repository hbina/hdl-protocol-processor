// External combinational program memory and synchronized inputs are supplied
// by the integrator. State is defined only after a synchronous reset edge.
module protocol_processor(
    input wire clk, reset,
    input wire [31:0] instruction,
    input wire [7:0] inputs,
    output reg [7:0] pc,
    output reg [15:0] wait_remaining,
    output reg [7:0] pins,
    output reg halted, fault,
    output reg [63:0] scratch,
    output reg [15:0] count,
    output reg [7:0] enables
);
    wire [7:0] next_pc, next_pins;
    wire [15:0] next_wait;
    wire next_halted, next_fault;
    wire [63:0] next_scratch;
    wire [15:0] next_count;
    wire [7:0] next_enables;
    processor_step core(
        .i_pc(pc), .i_wait(wait_remaining), .i_pins(pins),
        .i_halted(halted), .i_fault(fault), .i_instruction(instruction),
        .i_inputs(inputs), .o_next_pc(next_pc), .o_next_wait(next_wait),
        .o_next_pins(next_pins), .o_next_halted(next_halted), .o_next_fault(next_fault),
        .i_scratch(scratch), .o_next_scratch(next_scratch),
        .i_count(count), .o_next_count(next_count),
        .i_enables(enables), .o_next_enables(next_enables)
    );
    always @(posedge clk) begin
        if (reset) begin
            pc <= 0; wait_remaining <= 0; pins <= 0; halted <= 0; fault <= 0;
            scratch <= 0;
            count <= 0;
            enables <= 0;
        end else begin
            pc <= next_pc; wait_remaining <= next_wait; pins <= next_pins;
            halted <= next_halted; fault <= next_fault;
            scratch <= next_scratch;
            count <= next_count;
            enables <= next_enables;
        end
    end
endmodule
