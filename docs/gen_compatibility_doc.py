#!/usr/bin/env python
"""Render docs/compatibility.rst from docs/compatibility.yml.

Run with ``--check`` to exit non-zero when the committed rst is stale.
"""

import os
import sys

import yaml

DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
YAML_PATH = os.path.join(DOCS_DIR, "compatibility.yml")
RST_PATH = os.path.join(DOCS_DIR, "compatibility.rst")

STATUSES = {"expected", "tested", "broken", "n/a"}
MODALITY_TITLES = {
    "rest": "REST",
    "mq": "Message Queue (AMQP)",
    "relay": "Relay",
    "coexecution": "Coexecution",
    "embedded": "Embedded",
}

HEADER = """\
.. This file is generated from compatibility.yml by gen_compatibility_doc.py;
   edit the YAML and run ``make compatibility-docs``.

.. _compatibility:

------------------------------
Galaxy Compatibility
------------------------------

Each Galaxy release pins a ``pulsar-galaxy-lib`` version, the client half of
Pulsar. The tables below record, per Pulsar modality, which Pulsar servers
each Galaxy release is expected to work with. This is a best-effort record,
not a support guarantee.

Statuses:

``expected``
    Believed compatible from reading the code; not exercised by CI.
``tested``
    A CI job exercised this pairing.
``broken``
    A known break; see the linked issue.
``n/a``
    The modality does not exist for this Galaxy release.

Server ranges are `PEP 440 <https://peps.python.org/pep-0440/>`__ version
specifiers on the Pulsar server version. Servers older than 0.15.6 were not
surveyed. Issues listed against a range describe behavior changes or
configuration pitfalls for that pairing, many only relevant when an optional
feature is enabled.

The data lives in ``docs/compatibility.yml``.

Galaxy Releases
---------------

"""


def validate(data):
    errors = []
    releases = list(data["galaxy_releases"])
    issues = data["issues"]
    for name, modality in data["modalities"].items():
        matrix = modality.get("matrix")
        if matrix is None:
            continue
        if list(matrix) != releases:
            errors.append(f"{name}: matrix rows {list(matrix)} != galaxy_releases {releases}")
        for release, rows in matrix.items():
            for row in rows:
                if row.get("status") not in STATUSES:
                    errors.append(f"{name} {release}: unknown status {row.get('status')!r}")
                for issue in row.get("issues", []):
                    if issue not in issues:
                        errors.append(f"{name} {release}: undefined issue {issue!r}")
    return errors


def _issue_ref(issue_id):
    return f":ref:`{issue_id} <compat-issue-{issue_id}>`"


def _list_table(headers, rows):
    lines = [".. list-table::", "   :header-rows: 1", ""]
    for row in [headers, *rows]:
        lines.append(f"   * - {row[0]}")
        for cell in row[1:]:
            if isinstance(cell, list):
                bullets = [f"* {item}" for item in cell]
                lines.append(f"     - {bullets[0]}" if bullets else "     -")
                lines.extend(f"       {bullet}" for bullet in bullets[1:])
            else:
                lines.append(f"     - {cell}")
    return "\n".join(lines) + "\n"


def _galaxy_releases_table(data):
    rows = []
    for release, info in data["galaxy_releases"].items():
        lib = f"``{info['pulsar_galaxy_lib']}``"
        if info.get("planned"):
            lib += " (planned)"
        rows.append([release, lib])
    return _list_table(["Galaxy", "pulsar-galaxy-lib"], rows)


def _modality_section(name, modality, data):
    title = MODALITY_TITLES.get(name, name)
    out = [title, "-" * len(title), "", modality["description"].strip(), ""]
    if "contract" in modality:
        out += [f"Contract: {modality['contract']}", ""]
    if "default_image" in modality:
        image = modality["default_image"]
        out += [f"Default Pulsar image: ``{image['image']}`` (Pulsar {image['pulsar']}).", ""]
    for heading in ("backends", "other_axes"):
        if heading in modality:
            out += [f"{heading.replace('_', ' ').capitalize()}:", ""]
            out += [f"- ``{key}``: {value}" for key, value in modality[heading].items()]
            out.append("")
    matrix = modality.get("matrix")
    if matrix:
        peer = "Pulsar image" if "default_image" in modality else "Pulsar server"
        rows = []
        for release, entries in matrix.items():
            lib = f"``{data['galaxy_releases'][release]['pulsar_galaxy_lib']}``"
            for index, entry in enumerate(entries):
                peer_value = entry.get("servers") or entry.get("image") or ""
                notes = [_issue_ref(i) for i in entry.get("issues", [])]
                if entry.get("note"):
                    notes.append(entry["note"])
                rows.append(
                    [
                        release if index == 0 else "",
                        lib if index == 0 else "",
                        f"``{peer_value}``" if peer_value else "",
                        f"``{entry['status']}``",
                        notes,
                    ]
                )
        out.append(_list_table(["Galaxy", "pulsar-galaxy-lib", peer, "Status", "Issues"], rows))
    return "\n".join(out) + "\n"


def _issues_section(data):
    out = ["Known Issues", "------------", ""]
    for issue_id, issue in data["issues"].items():
        out += [f".. _compat-issue-{issue_id}:", "", f"``{issue_id}`` ({issue['severity']})"]
        out += ["   " + issue["summary"].strip(), ""]
    return "\n".join(out)


def render(data):
    parts = [HEADER, _galaxy_releases_table(data), "\n"]
    for name, modality in data["modalities"].items():
        parts += [_modality_section(name, modality, data), "\n"]
    parts.append(_issues_section(data))
    return "".join(parts)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    with open(YAML_PATH) as f:
        data = yaml.safe_load(f)
    errors = validate(data)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    rendered = render(data)
    if "--check" in argv:
        with open(RST_PATH) as f:
            if f.read() != rendered:
                print(f"{RST_PATH} is stale; run make compatibility-docs", file=sys.stderr)
                return 1
        return 0
    with open(RST_PATH, "w") as f:
        f.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
