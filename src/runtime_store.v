/* SPDX-License-Identifier: Apache-2.0 */
`default_nettype none
module runtime_store (
    input wire clk, input wire clear,
    input wire valid, input wire host, input wire write,
    input wire [15:0] address, input wire [7:0] data_in,
    input wire [31:0] debug_registers,
    output reg [7:0] data_out, output reg [3:0] error
);
  // Errors: address=3, denied=4, empty=5, full=6, incomplete=7, busy=8.
  reg [7:0] memory [0:255];
  reg pending;
  wire [7:0] in_head;
  wire [15:0] out_head;
  wire [6:0] in_count, out_count;
  wire [7:0] sub_head, event_head;
  wire [4:0] sub_staged, event_staged;
  wire [3:0] sub_cursor, event_cursor;
  wire sub_available, event_available;
  reg [7:0] output_data, output_metadata;
  reg data_staged, metadata_staged;
  // Qualify each side effect with its own permission/capacity checks. Feeding
  // the shared error-report mux back into every memory write creates a long
  // arbitration -> peripheral decode -> RAM write-enable path after mapping.
  wire host_write = valid && host && write;
  wire firmware_write = valid && !host && write;
  wire firmware_active = firmware_write && pending && !event_available;
  wire memory_write = valid && write && address[15:8] == 0 &&
      (host ? (!address[7] && !pending) : address[7]);
  wire flush = host_write && address == 16'h0100 && data_in == 1 && !pending;
  wire reset_queues = clear || flush;
  wire input_push = host_write && address == 16'h0110 && !pending && in_count < 64;
  wire input_pop = valid && !host && !write && address == 16'h0111 && pending && in_count != 0;
  wire output_push = firmware_active && address == 16'h0132 && data_in == 0 &&
      data_staged && metadata_staged && out_count < 64;
  wire output_pop = host_write && address == 16'h0135 && data_in == 0 && out_count != 0;
  wire sub_append = host_write && address == 16'h0120 && !pending && sub_staged < 16;
  wire sub_commit = host_write && address == 16'h0121 && data_in == 0 &&
      !pending && !sub_available && !event_available && out_count == 0 && sub_staged == 16;
  wire sub_pop = valid && !host && !write && address == 16'h0122 && sub_available;
  wire event_append = firmware_active && address == 16'h0140 && event_staged < 16;
  wire event_commit = firmware_active && address == 16'h0141 && data_in == 0 &&
      !sub_available && in_count == 0 && event_staged == 16;
  wire event_pop = valid && host && !write && address == 16'h0142 && event_available &&
      (event_cursor != 15 || out_count == 0);
  runtime_fifo input_fifo (.clk(clk), .clear(reset_queues),
      .push(input_push), .pop(input_pop), .data_in(data_in),
      .data_out(in_head), .count(in_count));
  runtime_fifo #(.WIDTH(16)) output_fifo (.clk(clk), .clear(reset_queues),
      .push(output_push), .pop(output_pop),
      .data_in({output_metadata, output_data}), .data_out(out_head), .count(out_count));
  runtime_record submissions (.clk(clk), .clear(reset_queues),
      .append(sub_append), .commit(sub_commit),
      .pop(sub_pop), .data_in(data_in),
      .data_out(sub_head), .staged(sub_staged), .cursor(sub_cursor), .available(sub_available));
  runtime_record events (.clk(clk), .clear(reset_queues),
      .append(event_append),
      .commit(event_commit), .pop(event_pop),
      .data_in(data_in), .data_out(event_head), .staged(event_staged),
      .cursor(event_cursor), .available(event_available));

  always @* begin
    data_out = 0; error = 0;
    if (address[15:8] == 0) begin
      data_out = memory[address[7:0]];
      if (host && address[7]) error = 4;
      else if (write && host && pending) error = 8;
      else if (write && !host && !address[7]) error = 4;
    end else begin
      case (address)
        16'h0100: begin
          if (!host || !write) error = 4;
          else if (data_in != 1) error = 2;
          else if (pending) error = 8;
        end
        16'h0101: data_out = {3'b000, event_available, sub_available,
                             out_count != 0, in_count != 0, pending};
        16'h0102: data_out = {1'b0, in_count};
        16'h0103: data_out = {1'b0, out_count};
        16'h0104: data_out = {7'b0, sub_available};
        16'h0105: data_out = {7'b0, event_available};
        16'h0106: data_out = 1;
        16'h0107: data_out = 128;
        16'h0108: data_out = 64;
        16'h0109: data_out = 16;
        16'h010a: data_out = 128;
        16'h010b: data_out = debug_registers[7:0];
        16'h010c: data_out = debug_registers[15:8];
        16'h010d: data_out = debug_registers[23:16];
        16'h010e: data_out = debug_registers[31:24];
        16'h0110: begin
          if (!host || !write) error = 4;
          else if (pending) error = 8;
          else if (in_count == 64) error = 6;
        end
        16'h0111: begin
          data_out = in_head;
          if (host || write) error = 4;
          else if (!pending || in_count == 0) error = 5;
        end
        16'h0120: begin
          if (!host || !write) error = 4;
          else if (pending) error = 8;
          else if (sub_staged == 16) error = 6;
        end
        16'h0121: begin
          if (!host || !write) error = 4;
          else if (data_in != 0) error = 2;
          else if (pending || sub_available || event_available || out_count != 0) error = 8;
          else if (sub_staged != 16) error = 7;
        end
        16'h0122: begin
          data_out = sub_head;
          if (host || write) error = 4;
          else if (!sub_available) error = 5;
        end
        16'h0130, 16'h0131: begin
          if (host || !write) error = 4;
          else if (!pending || event_available) error = 8;
        end
        16'h0132: begin
          if (host || !write) error = 4;
          else if (data_in != 0) error = 2;
          else if (!pending || event_available) error = 8;
          else if (!data_staged || !metadata_staged) error = 7;
          else if (out_count == 64) error = 6;
        end
        16'h0133, 16'h0134: begin
          data_out = address[0] ? out_head[7:0] : out_head[15:8];
          if (!host || write) error = 4;
          else if (out_count == 0) error = 5;
        end
        16'h0135: begin
          if (!host || !write) error = 4;
          else if (data_in != 0) error = 2;
          else if (out_count == 0) error = 5;
        end
        16'h0140: begin
          if (host || !write) error = 4;
          else if (!pending || event_available) error = 8;
          else if (event_staged == 16) error = 6;
        end
        16'h0141: begin
          if (host || !write) error = 4;
          else if (data_in != 0) error = 2;
          else if (!pending || event_available || sub_available || in_count != 0) error = 8;
          else if (event_staged != 16) error = 7;
        end
        16'h0142: begin
          data_out = event_head;
          if (!host || write) error = 4;
          else if (!event_available) error = 5;
          else if (event_cursor == 15 && out_count != 0) error = 8;
        end
        default: error = 3;
      endcase
      if (address >= 16'h0101 && address <= 16'h010e && write) error = 4;
    end
  end
  always @(posedge clk) begin
    if (reset_queues) begin
      pending <= 0; data_staged <= 0; metadata_staged <= 0;
      output_data <= 0; output_metadata <= 0;
    end else begin
      if (sub_commit) pending <= 1;
      if (event_pop && event_cursor == 15) begin
        pending <= 0; data_staged <= 0; metadata_staged <= 0;
      end
      if (memory_write) memory[address[7:0]] <= data_in;
      if (firmware_active && address == 16'h0130) begin output_data <= data_in; data_staged <= 1; end
      if (firmware_active && address == 16'h0131) begin output_metadata <= data_in; metadata_staged <= 1; end
      if (output_push) begin data_staged <= 0; metadata_staged <= 0; end
    end
  end
endmodule
`default_nettype wire
