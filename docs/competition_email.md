# Competition organizer update and FAQ

Source: email signed by Ben and Anish, supplied by the project owner.
Email subject and sent/received date were not supplied. Archived in this
repository on 2026-10-24.

The email body below is preserved as supplied, with Markdown formatting added.
Statements about template availability, tooling, pad characterization, and
planned dates describe the organizer update at the time it was sent; this
archive does not independently confirm their current status. In particular,
the expected mid-October availability of 8x4 is not confirmation of release.

## Email body

Hi everyone,

Thanks for signing up for the protocol emulator ASIC competition, and for all the questions so far! Here's a quick update, followed by answers to the most common questions.

### Update

- 8x4 template: Tiny Tapeout expects the 8x4 CMOS5L template to be ready around mid-October. Until then, keep designing to 6x4 and treat 8x4 as an upgrade. We'll email again when it's out.
- SRAM: Ken Pettit has written a walkthrough on adding an IHP SRAM macro to a CMOS5L tile, covering the RTL, LibreLane config, Metal4 power and sign-off: https://kdp1965.github.io/ihp-um-janestreet-prism/ihp_sram_macro.html
- Dev board: Winners will get the latest Tiny Tapeout ETR demo board with their fabricated chip mounted on it.
- GDS action: The CMOS5L install problem some people hit in the Tiny Tapeout GDS action was fixed a few weeks ago. If you saw it, rerun with the latest action.
- I/O: CMOS5L is new enough that there's no silicon back yet, so there aren't characterized numbers for the pads. Tiny Tapeout is checking whether they have numbers from the similar SG13G2 process.
- We plan to update the blog with these details in the following weeks, and we'll add the submission form closer to the January 18th deadline.

### FAQ

#### Entering

**Who can enter, and how big can teams be?**

Students and professionals are both welcome. You can enter on your own or as a team, and there's no limit on team size. Each team submits one entry.

**Did my sign-up go through?**

If you're reading this, yes. The form doesn't send a confirmation email, and there's nothing else you need to do to register. The sign-up is just so we can send updates.

**Can you review my architecture before I submit?**

To keep things fair we can't review individual designs before the deadline, but feel free to email us specific questions.

#### Design

**How much area do I have?**

Our planned maximum is 8x4 tiles. Design to 6x4 until the 8x4 template is out (see the update above).

**Can I use SRAM macros?**

Yes, you can use the IHP SRAM macros, including more than one, as long as everything fits in your tiles and passes the Tiny Tapeout precheck. Ken's walkthrough (linked above) uses two of them.

**What pins are available?**

24 digital pins: 8 inputs, 8 outputs and 8 bidirectional, plus clock and reset. There are no analog pads, but analog or mixed-signal circuits inside your design (like a PLL) are fine as long as they pass precheck.

**Can I use external parts on the board?**

Yes. The chip only has digital pins (3.3V I/O on the demo board), so things like pull-ups, transceivers or level shifting go on a Pmod. Tiny Tapeout's Pmods and recommended pinouts are good examples of what's possible. Please document anything your design needs. Pmods and the demo board: https://tinytapeout.com/specs/pcb-etr/ Pinouts: https://tinytapeout.com/specs/pinouts/

**What clock frequency should I target?**

There's no target. Pick one that closes timing after place-and-route and meets the protocols you want to support.

**Does it have to be a CPU?**

No. A CPU-style design is the most common approach, but an eFPGA, multiple engines sharing a pipeline, or something else entirely is fine, as long as the chip can be reprogrammed after fabrication to support new protocols. Whatever you build, include the software side: an assembler or toolchain (or bitstream flow) and example programs for the protocols you support.

**Which protocols, and how fast?**

Start with UART, SPI and I2C. Stretch goals are low-speed USB and 10 Mbit Ethernet. There are no fixed speed requirements, and standard settings (common UART baud rates, SPI modes 0-3, I2C at 100 and 400 kHz) are a good target. Running protocols concurrently, or supporting both controller and target roles, is a plus but not required. For USB and Ethernet, the more of the protocol work (line coding, CRC, clock recovery) your chip does itself, the better.

**How does the program get loaded?**

That's part of your design. The microcontroller on the demo board is the natural host, but any documented host works.

**What about reset and power?**

Unlike an FPGA, flops don't start at 0, so your design needs to use the reset signal (rst_n) to get into a known state. On the demo board it's triggered by a button or from software. When your design is deselected it's powered down and loses its state, so plan to reload the program after it's selected again. Tiny Tapeout has more on moving from FPGA to ASIC here: https://tinytapeout.com/hdl/fpga_vs_asic/

#### Submission and judging

**What do I submit?**

A link to your public repository with your RTL, tests and a passing GDS/precheck from the Tiny Tapeout flow. Please also include documentation of your architecture and instruction set, your assembler or toolchain with example programs, and a write-up of your verification approach. A video or demo isn't required, but we'll look at it if you have one.

**Can I use my own GDS flow?**

Please stick to the Tiny Tapeout flow, since that's how the winning designs get onto the shuttle. GitHub Actions have a 6 hour limit, and a design that's close to full can hit it. If that happens, you can run the same Tiny Tapeout flow locally: https://tinytapeout.com/guides/local-hardening/

**Does my repo need to be public now?**

No. You can develop privately and make the repo public when you submit, or build in public if you prefer.

**How will entries be judged?**

There's no fixed weighting. Flexibility is the main thing: can the chip be reprogrammed to support protocols it wasn't designed for? Beyond that, we'll look at which protocols you demonstrate, anything unique your architecture makes possible, and how you designed and verified it. A design with fewer protocols but a strong architecture and verification approach can definitely be competitive.

**Can I use AI tools?**

Yes. Please describe how you used them in your write-up.

**Can my design also go on another shuttle?**

Yes, as long as your competition entry is its own open-source CMOS5L submission by January 18th.

#### Timeline and prizes

- Submissions close January 18th, 2027.
- We're aiming to announce the selected designs in early February, ahead of the March 2027 CMOS5L shuttle.
- We're currently planning to tape out around four designs (this could still change). Winners will receive their chips on the Tiny Tapeout demo board.
- After the deadline, small non-functional fixes like re-hardening for a newer flow are fine, and we'll work with the winners on those.

If you're looking for teammates or want to chat with other entrants, the Tiny Tapeout Discord has a competitions channel. For anything else, reply to this email or reach us at asic-competition@janestreet.com.

Thanks,
Ben and Anish
