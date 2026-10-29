"""Privacy Research components: detection rules, Presidio, merge, calibration, decision and the
context store. Each depends only on `contracts/`; `main.build_components` wires them in.
Prompts and parsers belong to Model Work. Restore keeps the stub version, which already meets the exact-match
contract; pseudonymisation adds header-name variant grouping.
"""
from .calibration import fit_table, load_table, make_calibrate
from .context_store import FileContextStore
from .decide import decide
from .merge import make_merge
from .presidio import make_detect_presidio
from .pseudonymize import pseudonymize
from .rules import detect_rules, marked_passages

__all__ = ["FileContextStore", "decide", "detect_rules", "fit_table", "load_table",
           "make_calibrate", "make_detect_presidio", "make_merge", "marked_passages", "pseudonymize"]
