`default_nettype none
module tt_um_combhdl_demo (
    input wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input wire ena,
    input wire clk,
    input wire rst_n
);
    combhdl_demo demo (
        .a(ui_in[3:0]),
        .b(ui_in[7:4]),
        .choose(uio_in[0]),
        .shared(uo_out[7:4]),
        .result(uo_out[3:0])
    );
    assign uio_out = 8'h00;
    assign uio_oe = 8'h00;
    wire _unused = &{ena, clk, rst_n, uio_in[7:1], 1'b0};
endmodule
`default_nettype wire
