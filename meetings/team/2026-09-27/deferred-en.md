# Deferred from the Sep 27 agenda

Two conflicts were taken off tonight's agenda so the session can finish items 1, 2, 3 and 6.
Neither blocks what we say to the client tomorrow. Both still need settling.

Full write-ups were in the agenda at commit `f2c87e9`; this is the summary.

## A. State storage — three names, or three different things

| Who | Name | Holds | Scope | Lifetime |
|---|---|---|---|---|
| Zhexuan | `session mapping` | placeholder label consistency | one session | bounded |
| Karina | `vault` | placeholder → real value | one session | cleared at session end |
| **Zhexuan** | **`global context store`** | **known entities, private information** | **across sessions and callers** | **persistent** |

The first two are the same component under two names. The third is new.

**Proposed:** call the first two `vault`. Do not build the global context store in v0 —
it is persistent where the vault is not, its encryption/retention/access control are
unspecified, cross-caller sharing is a privacy problem nobody asked for, and the core
flow works without it. Move it to a later phase with its own security design.

**Concrete problem:** if the CEO's assistant and the CFO's assistant share one context
store, does a lookup on a person from the CFO side return what was recorded on the
CEO side? No client document asks for that.

**Owner:** Zhexuan

## B. Who owns the confidence score, and whose version

Three people wrote a version; per `todo/TODO.md` A9 it is Anmol's area 3. This happened
because Anmol is blocked on hardware (D24) and produced no document, not because three
people want to own it.

On the same span (`Harborview`, raw 0.55) the three methods give three numbers:
Yudi's calibration reports 0.30, Karina's detector-vote share gives 0.33, Zhexuan's API
field just says 0.55 with no method attached.

**Proposed split along workstream boundaries:**

| Step | Owner | Whose version |
|---|---|---|
| Produce the raw score | Anmol (area 3) | His implementation, PR #2 signal priority |
| Calibration procedure | Yudi supplies, Anmol implements | Yudi's — most complete, has a fallback method |
| Choosing the threshold | Karina (area 1) | A threshold is an evaluation output |
| The API field | Zhexuan (area 4) | Carries the **calibrated** score; spec must say so |

Add a `score_method` field to each span, or nobody reading a 0.55 can tell what it is.

**Knock-on:** `todo/TODO.md` B33's handover widens — not only Zhexuan's PR #2 but
Yudi's calibration procedure too.

**Owner:** Anmol
