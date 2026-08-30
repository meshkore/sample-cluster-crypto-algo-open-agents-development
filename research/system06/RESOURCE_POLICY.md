# How this machine is used

Operator, 2026-08-30: the whole box - CPU, GPU, RAM - exists for this work. Use it
fully and continuously; idle capacity is waste, but a crash costs more than it saves.

Hardware: RTX 4060 (8 GB VRAM), 12 logical cores, 32 GB RAM.

## The rule that came from measurement, not taste

ONE heavy TRAINING at a time on the GPU beyond the standing circuit. Everything else
runs in parallel on CPU.

Why: three concurrent trainings cost P22 a MemoryError (a 101 MiB allocation refused
on a 32 GB box) and stretched a single epoch past fifteen minutes, which also nearly
produced a false "dead daemon" alarm. Two is the measured comfortable limit.

## The standing circuit (always up, watchdog-guarded)

  autoloop        - genome search, GPU
  autotest runner - queued experiments, GPU
  pulse           - hourly trace, negligible
  cf_pusher       - publishes the dashboard, negligible
  wall_listener   - cluster inbox, negligible

## What to run in parallel, safely

  * backtests and per-year evaluations (CPU-bound; several at once is fine and is
    the cheapest way to use the other cores)
  * inference passes (seconds of GPU, then CPU)
  * analyses over existing artifacts (trade maps, channel joins, sweeps)

## What NOT to do

  * a third training process while the circuit is training - queue it into the
    runner instead (that is what rnd/program.jsonl is for)
  * starting a long job by hand without checking whether one is already running:
    that produced a duplicate pulse daemon and a duplicate champion attempt
