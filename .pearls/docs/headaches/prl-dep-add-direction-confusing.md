# prl dep add positional direction is easy to get backwards

> Captured: 2026-11-28

## What was happening

While refining epic gsv-1fc3 I ran `prl dep add gsv-1fc3.2 gsv-1fc3.1` to say that gsv-1fc3.2 depends on gsv-1fc3.1. prl recorded "gsv-1fc3.2 blocks gsv-1fc3.1", the opposite. I removed both dependencies and added them again with `--blocked-by`.

## Headache

`prl dep add A B` reads as "A depends on B", but it records "A blocks B". The positional form should match the "A depends on B" reading, or it should print which way the dependency goes and ask before recording it.
