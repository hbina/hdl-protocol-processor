/* SPDX-License-Identifier: Apache-2.0 */
`default_nettype none
module runtime_fifo #(
    parameter WIDTH = 8, parameter DEPTH = 64,
    parameter PTR_BITS = DEPTH > 1 ? $clog2(DEPTH) : 1
) (
    input wire clk, input wire clear,
    input wire push, input wire pop,
    input wire [WIDTH-1:0] data_in,
    output wire [WIDTH-1:0] data_out,
    output reg [PTR_BITS:0] count
);
  localparam [PTR_BITS-1:0] LAST_INDEX = DEPTH[PTR_BITS-1:0] - 1'b1;
  localparam [PTR_BITS:0] CAPACITY = DEPTH[PTR_BITS:0];
  reg [WIDTH-1:0] entries [0:DEPTH-1];
  reg [PTR_BITS-1:0] rd, wr;
  wire accept_push = push && count < CAPACITY;
  wire accept_pop = pop && count != 0;
  assign data_out = entries[rd];
  always @(posedge clk) begin
    if (clear) begin rd <= 0; wr <= 0; count <= 0; end
    else begin
      if (accept_push) begin
        entries[wr] <= data_in;
        wr <= wr == LAST_INDEX ? 0 : wr + 1'b1;
      end
      if (accept_pop) rd <= rd == LAST_INDEX ? 0 : rd + 1'b1;
      case ({accept_push, accept_pop})
        2'b10: count <= count + 1'b1;
        2'b01: count <= count - 1'b1;
        default: begin end
      endcase
    end
  end
endmodule

// A depth-one opaque record FIFO with private producer staging.
module runtime_record (
    input wire clk, input wire clear,
    input wire append, input wire commit, input wire pop,
    input wire [7:0] data_in,
    output wire [7:0] data_out,
    output reg [4:0] staged,
    output reg [3:0] cursor,
    output reg available
);
  reg [7:0] staging [0:15];
  reg [7:0] record_data [0:15];
  integer i;
  assign data_out = record_data[cursor];
  always @(posedge clk) begin
    if (clear) begin staged <= 0; cursor <= 0; available <= 0; end
    else begin
      if (append && staged < 16) begin
        staging[staged[3:0]] <= data_in;
        staged <= staged + 1'b1;
      end
      if (commit && staged == 16 && !available) begin
        for (i = 0; i < 16; i = i + 1) record_data[i] <= staging[i];
        staged <= 0; cursor <= 0; available <= 1;
      end
      if (pop && available) begin
        if (cursor == 15) begin available <= 0; cursor <= 0; end
        else cursor <= cursor + 1'b1;
      end
    end
  end
endmodule
`default_nettype wire
