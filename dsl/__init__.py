"""DSL actuarial guest domain (G1–G3 + G5 files + G6 auth).

Not a getafix-seed-paul / dsl-work lift. HTTP JSON on the Unit public
port. Opaque work handoff is kind/class/payload_digest
(runtime/compute_work.py on panoramix-runtime main). Specs catalog is
the platform.ts intention without Getafix. G5 files browse is
read-first specs/data/results over fixture/catalog paths. G6 is a
thin local-lab login gate (hmac tokens) — not Cognito. Compute
engines stay in panoramix-runtime bindings. Epic #1 remains open.
Does not unlock runtime #61 / #29.
"""

__version__ = "0.1.0"
