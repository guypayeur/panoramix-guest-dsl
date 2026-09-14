"""DSL actuarial guest domain (G1 jobs + G2 specs + G6 auth + G3 editor).

Not a getafix-seed-paul / dsl-work lift. HTTP JSON on the Unit public
port. Opaque work handoff is kind/class/payload_digest
(runtime/compute_work.py on panoramix-runtime main). Specs catalog is
the platform.ts intention without Getafix. G6 is a thin local-lab
login gate (hmac tokens) — not Cognito. Compute engines stay in
panoramix-runtime bindings. Does not close epic #1. Does not unlock
runtime #61 / #29.
"""

__version__ = "0.1.0"
