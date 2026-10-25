/* SPDX-License-Identifier: Apache-2.0 */
`default_nettype none
module runtime_bridge (
    input wire clk, input wire clear,
    input wire request, input wire [5:0] token,
    output wire [7:0] response,
    output reg valid, output reg write,
    output reg [15:0] address, output reg [7:0] data_in,
    input wire ready, input wire [7:0] data_out, input wire [3:0] error
);
  (* async_reg = "true", keep = "true" *) reg request_meta, request_sync;
  reg ack, settling, response_error;
  reg [5:0] response_data;
  reg [2:0] phase;
  reg [7:0] read_value;
  assign response = {ack, response_error, response_data};
  always @(posedge clk) begin
    if (clear) begin
      request_meta <= 0; request_sync <= 0; ack <= 0; settling <= 0;
      response_error <= 0; response_data <= 0; phase <= 0;
      valid <= 0; write <= 0; address <= 0; data_in <= 0; read_value <= 0;
    end else begin
      request_meta <= request;
      request_sync <= request_meta;
      if (valid) begin
        if (ready) begin
          valid <= 0; ack <= request_sync;
          response_error <= error != 0;
          response_data <= error != 0 ? {2'b0, error} : (write ? 6'b0 : data_out[5:0]);
          read_value <= data_out;
          phase <= error != 0 || write ? 0 : 7;
        end
      end else if (request_sync != ack) begin
        if (!settling) settling <= 1;
        else begin
          settling <= 0; ack <= request_sync;
          response_error <= 0; response_data <= 0;
          case (phase)
            0: begin
              if (token > 1) begin response_error <= 1; response_data <= 1; end
              else begin write <= token[0]; phase <= 1; end
            end
            1: begin address[5:0] <= token; phase <= 2; end
            2: begin address[11:6] <= token; phase <= 3; end
            3: begin
              if (token[5:4] != 0) begin phase <= 0; response_error <= 1; response_data <= 2; end
              else begin
                address[15:12] <= token[3:0];
                if (write) phase <= 4;
                else begin valid <= 1; ack <= ack; end
              end
            end
            4: begin data_in[5:0] <= token; phase <= 5; end
            5: begin
              if (token[5:2] != 0) begin phase <= 0; response_error <= 1; response_data <= 2; end
              else begin data_in[7:6] <= token[1:0]; valid <= 1; ack <= ack; end
            end
            7: begin
              phase <= 0;
              if (token != 0) begin response_error <= 1; response_data <= 2; end
              else response_data <= {4'b0, read_value[7:6]};
            end
            default: phase <= 0;
          endcase
        end
      end
    end
  end
endmodule
`default_nettype wire
