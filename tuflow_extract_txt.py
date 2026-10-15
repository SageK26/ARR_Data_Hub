"""
TUFLOW Storm Losses / Burst Initial Loss extractor -- TEXT FILE VERSION.

This version parses the plain-text ARR Data Hub export format (the
"Results - ARR Data Hub" .txt download), NOT a PDF. This format is far
more reliable to parse than scraping a PDF, since every section is
delimited by explicit [SECTION] / [END_SECTION] markers and the data is
plain comma-separated text rather than reconstructed table geometry.

Python 3.9+, dependencies: none (standard library only).

Sections used:
    [NEWLOSSES] ... [END_NEWLOSSES]       -> Storm Losses (AEP, Preburst,
                                              Storm Initial Loss, CL)
    [BURSTILNEW] ... [END_BURSTILNEW]     -> Burst Initial Loss matrix
                                              (duration x AEP grid)

Usage (plain terminal):
    python tuflow_extract_txt.py input.txt
    python tuflow_extract_txt.py input.txt --trd my_losses.trd

Usage (Jupyter/IPython notebook cell):
    from tuflow_extract_txt import run
    run("input.txt")
    run("input.txt", trd_path="my_losses.trd")
"""

import re
import sys
import argparse
from pathlib import Path


AEP_DISPLAY_ORDER = ["50p", "20p", "10p", "5p", "2p", "1p"]
AEP_DISPLAY_LABEL = {
    "50p": "50.0p",
    "20p": "20.0p",
    "10p": "10.0p",
    "5p": "5.0p",
    "2p": "2.0p",
    "1p": "1.0p",
}
VALID_AEPS = set(AEP_DISPLAY_ORDER)

DURATION_ORDER = [
    "30 min", "60 min", "90 min", "120 min", "180 min",
    "6 hr", "12 hr", "18 hr", "24 hr", "36 hr", "48 hr", "72 hr",
]

MINUTES_TO_LABEL = {
    30: "30 min", 60: "60 min", 90: "90 min", 120: "120 min", 180: "180 min",
    360: "6 hr", 720: "12 hr", 1080: "18 hr", 1440: "24 hr",
    2160: "36 hr", 2880: "48 hr", 4320: "72 hr",
}


def normalise_text(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def clean_aep(aep):
    """
    Normalise an AEP label (e.g. '50.0', '50.0%', '50%') to one of
    '50p','20p','10p','5p','2p','1p'. Returns '' if unrecognised.
    """
    s = normalise_text(aep).lower()
    if not s:
        return ""
    s = s.replace("%", "p").replace(" ", "")
    if not s.endswith("p"):
        m = re.match(r"^(\d+(?:\.\d+)?)$", s)
        if m:
            num = float(m.group(1))
            candidate = f"{int(num)}p"
            return candidate if candidate in VALID_AEPS else ""
        return ""
    s = re.sub(r"\.0+p$", "p", s)
    m = re.match(r"^(\d+(?:\.\d+)?)p$", s)
    if not m:
        return ""
    num = m.group(1)
    if num.endswith(".0"):
        num = num[:-2]
    candidate = f"{num}p"
    return candidate if candidate in VALID_AEPS else ""


def normalise_duration_label(raw):
    """
    Turn a duration cell like '30', '30 (0.5)', '1080 (18.0)' into a
    canonical label from DURATION_ORDER. The ARR Data Hub text format
    always uses the 'MINUTES (HOURS)' compound style for this field.
    """
    s = normalise_text(raw).lower()
    if not s:
        return ""
    m_compound = re.match(r"^(\d+(?:\.\d+)?)\s*\([^)]*\)$", s)
    if m_compound:
        s = m_compound.group(1)
    else:
        m_plain = re.match(r"^(\d+(?:\.\d+)?)$", s)
        if not m_plain:
            return ""
        s = m_plain.group(1)
    num = int(float(s))
    return MINUTES_TO_LABEL.get(num, "")


def extract_il_value(cell):
    """
    Extract the Initial Loss value from a Burst Initial Loss cell.
    Returns the plain number if present, otherwise 'Use PB TP' for any
    non-numeric placeholder (including the literal 'Use PB TP' text
    itself, blanks, dashes, or anything else).
    """
    s = normalise_text(cell)
    m = re.match(r"^[-+]?\d+(?:\.\d+)?$", s)
    if m:
        return m.group(0)
    return "Use PB TP"


def extract_section(text, section_name):
    """
    Extract the raw lines between [SECTION_NAME] and [END_SECTION_NAME]
    markers (case-sensitive, matching the ARR Data Hub export format
    exactly). Returns a list of lines, or None if the section is not
    found.
    """
    start_marker = f"[{section_name}]"
    end_marker = f"[END_{section_name}]"
    lines = text.splitlines()

    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if line.strip() == start_marker and start_idx is None:
            start_idx = i
        elif line.strip() == end_marker and start_idx is not None:
            end_idx = i
            break

    if start_idx is None or end_idx is None:
        return None

    return lines[start_idx + 1:end_idx]


def parse_storm_losses(text):
    """
    Parse the [NEWLOSSES] section into a CL lookup: {aep: cl_value}.

    Expected format:
        Region,Macquarie/Lachlan
        AEP,Preburst,Storm Initial Loss (mm),Continuing Loss (mm/h)
        1%,75%,30,1.0
        ...
    """
    lines = extract_section(text, "NEWLOSSES")
    if lines is None:
        raise RuntimeError(
            "Could not find [NEWLOSSES] ... [END_NEWLOSSES] section in the input file."
        )

    header_idx = None
    for i, line in enumerate(lines):
        cols = [c.strip().lower() for c in line.split(",")]
        if cols and cols[0] == "aep":
            header_idx = i
            break

    if header_idx is None:
        raise RuntimeError("Could not locate the 'AEP,Preburst,...' header row inside [NEWLOSSES].")

    header_cols = [c.strip().lower() for c in lines[header_idx].split(",")]
    cl_col_idx = None
    for idx, col in enumerate(header_cols):
        if "continuing loss" in col:
            cl_col_idx = idx
            break
    if cl_col_idx is None:
        raise RuntimeError("Could not find a 'Continuing Loss' column inside [NEWLOSSES].")

    lookup = {}
    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        cols = [c.strip() for c in line.split(",")]
        if not cols or not cols[0]:
            continue
        aep = clean_aep(cols[0])
        if not aep:
            continue
        if cl_col_idx >= len(cols):
            continue
        cl_value = normalise_text(cols[cl_col_idx])
        if cl_value:
            lookup[aep] = cl_value

    if not lookup:
        raise RuntimeError("Parsed [NEWLOSSES] section but found no usable AEP/Continuing Loss rows.")

    return lookup


def parse_burst_initial_loss(text):
    """
    Parse the [BURSTILNEW] section into an IL lookup:
    {aep: {duration: value}}.

    Expected format:
        min (h)\\AEP(%),50.0,20.0,10.0,5.0,2.0,1.0
        30 (0.5),29.5,26.4,16.9,16.4,19.9,25.3
        ...
    """
    lines = extract_section(text, "BURSTILNEW")
    if lines is None:
        raise RuntimeError(
            "Could not find [BURSTILNEW] ... [END_BURSTILNEW] section in the input file."
        )

    header_idx = None
    header_cols = None
    for i, line in enumerate(lines):
        cols = [c.strip() for c in line.split(",")]
        aep_hits = sum(1 for c in cols if clean_aep(c) in VALID_AEPS)
        if aep_hits >= 2:
            header_idx = i
            header_cols = cols
            break

    if header_idx is None:
        preview = "\n".join(f"  {l}" for l in lines[:10])
        raise RuntimeError(
            "Could not locate the AEP header row inside [BURSTILNEW] "
            f"(need at least 2 recognisable AEP columns).\nFirst lines seen:\n{preview}"
        )

    aep_cols = []
    for idx, val in enumerate(header_cols):
        c = clean_aep(val)
        if c in VALID_AEPS:
            aep_cols.append((idx, c))

    if not aep_cols:
        raise RuntimeError(f"Header row found but no AEP columns could be mapped: {header_cols}")

    lookup = {}
    unmatched_rows = []

    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        cols = [c.strip() for c in line.split(",")]
        if not cols or not cols[0]:
            continue

        duration = normalise_duration_label(cols[0])
        if not duration:
            unmatched_rows.append(cols[0])
            continue

        for idx, aep in aep_cols:
            if idx >= len(cols):
                continue
            value = extract_il_value(cols[idx])
            if value:
                lookup.setdefault(aep, {})[duration] = value

    if not lookup:
        preview = "\n".join(f"  '{r}'" for r in unmatched_rows[:15])
        raise RuntimeError(
            "AEP header row found but no duration rows produced values.\n"
            f"Unmatched first-column values seen:\n{preview}"
        )

    return lookup


def generate_tuflow_code(cl_lookup, il_lookup):
    """
    Generate the nested AEP x duration TUFLOW code, with every duration
    found in the Burst Initial Loss table included by default under its
    AEP:

        If Event == 50.0p
            if duration == 30 min
                Set Variable CL == 2.75
                Set Variable IL == 29.5
            if duration == 60 min
                Set Variable CL == 2.75
                Set Variable IL == 29.4
        End If
        If Event == 20.0p
            ...
        End If
    """
    lines = []
    pb_tp_entries = []
    skipped = []

    for aep in AEP_DISPLAY_ORDER:
        if aep not in cl_lookup:
            skipped.append(f"{aep}: no Continuing Loss value found")
            continue
        if aep not in il_lookup:
            skipped.append(f"{aep}: no Initial Loss value found")
            continue

        label = AEP_DISPLAY_LABEL[aep]
        cl_value = cl_lookup[aep]
        durations_present = il_lookup[aep]

        ordered_durations = [d for d in DURATION_ORDER if d in durations_present]
        ordered_durations += [d for d in durations_present if d not in DURATION_ORDER]

        if not ordered_durations:
            skipped.append(f"{aep}: no durations found in Initial Loss table")
            continue

        lines.append(f"If Event == {label}")

        for duration in ordered_durations:
            il_value = durations_present[duration]
            lines.append(f"    if duration == {duration}")
            lines.append(f"        Set Variable CL == {cl_value}")

            if il_value.strip().lower() == "use pb tp":
                lines.append("        Set Variable IL == PB_TP")
                pb_tp_entries.append(f"{label} / {duration}")
            else:
                lines.append(f"        Set Variable IL == {il_value}")

        lines.append("End If")

    return "\n".join(lines), pb_tp_entries, skipped


def write_trd_file(cl_lookup, il_lookup, out_path, source_name=""):
    """
    Write the extracted IL and CL data (and the generated TUFLOW code)
    to a .trd text file, with a documentation header noting units,
    source, and any PB_TP (preburst temporal pattern) substitutions.
    """
    tuflow_code, pb_tp_entries, skipped = generate_tuflow_code(cl_lookup, il_lookup)

    header_lines = [
        f"! {Path(out_path).name}",
        "! Rainfall losses (Initial Loss / Continuing Loss) by AEP and burst duration",
    ]
    if source_name:
        header_lines.append(f"! Generated from ARR Data Hub text export: {source_name}")
    header_lines += [
        "! IL units: mm   CL units: mm/h",
        "! PB_TP = Use Preburst Temporal Pattern (no fixed IL value available for this AEP/duration)",
        "!",
    ]

    if pb_tp_entries:
        header_lines.append("! AEP / duration combinations using PB_TP instead of a fixed IL value:")
        for entry in pb_tp_entries:
            header_lines.append(f"!   {entry}")
        header_lines.append("!")

    full_content = "\n".join(header_lines) + "\n" + tuflow_code + "\n"
    Path(out_path).write_text(full_content, encoding="utf-8")
    return out_path, pb_tp_entries, skipped


def _running_under_notebook():
    if "ipykernel" in sys.modules or "IPython" in sys.modules:
        return True
    return any(a.startswith("-f") or "ipykernel" in a or "connection-file" in a for a in sys.argv[1:])


def run(txt_path, trd_path=None):
    """
    Notebook-safe entry point.

        from tuflow_extract_txt import run
        run("input.txt")
        run("input.txt", trd_path="my_losses.trd")

    Parameters
    ----------
    txt_path : str or Path
        Path to the input ARR Data Hub .txt export.
    trd_path : str or Path or None
        Output .trd file path. Defaults to 'rainfall_losses.trd' in the
        current working directory if not given.
    """
    path = Path(txt_path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    _process(path, trd_path=trd_path)


def parse_cli_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract TUFLOW Storm Losses / Burst Initial Loss data from an ARR Data Hub .txt export."
    )
    parser.add_argument("txt", type=str, help="Path to the input .txt file.")
    parser.add_argument(
        "--trd",
        type=str,
        default="rainfall_losses.trd",
        help="Output .trd file path (default: rainfall_losses.trd).",
    )
    return parser.parse_args(argv)


def main():
    if _running_under_notebook():
        raise SystemExit(
            "Detected a Jupyter/IPython kernel. Command-line argument parsing is skipped "
            "automatically here because sys.argv contains kernel-launcher arguments, not your "
            "file path.\n\n"
            "Instead, call the function directly in a notebook cell, for example:\n\n"
            "    from tuflow_extract_txt import run\n"
            "    run(\"input.txt\")\n"
            "    run(\"input.txt\", trd_path=\"my_losses.trd\")\n"
        )
    args = parse_cli_args(sys.argv[1:])
    path = Path(args.txt)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    _process(path, trd_path=args.trd)


def _process(path, trd_path=None):
    text = path.read_text(encoding="utf-8", errors="replace")

    cl_lookup = parse_storm_losses(text)
    il_lookup = parse_burst_initial_loss(text)

    print("Extracted CL lookup:")
    for k, v in cl_lookup.items():
        print(f"{k}: {v}")

    print("\nExtracted IL lookup:")
    for aep, durations in il_lookup.items():
        print(f"{aep}: {durations}")

    print("\nUnits:")
    print("- IL: mm")
    print("- CL: mm/h")
    print("Note: CL values were extracted from the [NEWLOSSES] section of this ARR Data Hub text export.\n")

    if trd_path is None:
        trd_path = "rainfall_losses.trd"

    out_path, pb_tp_entries, skipped = write_trd_file(cl_lookup, il_lookup, trd_path, source_name=path.name)

    print(f"Saved IL/CL data and generated TUFLOW code to: {out_path}\n")

    print("PB_TP entries:")
    if pb_tp_entries:
        for entry in pb_tp_entries:
            print(f"- {entry}")
    else:
        print("- None")

    if skipped:
        print("\nSkipped AEPs (missing data):")
        for s in skipped:
            print(f"- {s}")


if __name__ == "__main__":
    main()
