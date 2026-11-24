#!/usr/bin/env python3
"""make_manifest.py — write outputs/run-manifest.json: the deterministic run
manifest. No timestamps. Contains the pinned commit, the full SHA-256 of
every input (scenario files, scripts) and of every output file, so a
re-run can be checked for byte-identical reproduction without trusting
any single log line.
"""

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
OUTPUTS_DIR = os.path.join(PACK, "outputs")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    inputs = {}
    for d in ("scenarios", "scripts"):
        for name in sorted(os.listdir(os.path.join(PACK, d))):
            p = os.path.join(PACK, d, name)
            if os.path.isfile(p):
                inputs["%s/%s" % (d, name)] = sha256_file(p)
    outputs = {}
    for name in sorted(os.listdir(OUTPUTS_DIR)):
        p = os.path.join(OUTPUTS_DIR, name)
        if os.path.isfile(p) and name not in ("run_all.log", "run-manifest.json"):
            outputs["outputs/%s" % name] = sha256_file(p)
    manifest = {
        "pinned_commit": "0085a1ff885d6a446369cf73a4430f75af22be55",
        "pinned_commit_date": "2026-10-10",
        "pinned_commit_message": "Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9",
        "simulated": True,
        "inputs": inputs,
        "outputs": outputs,
    }
    with open(os.path.join(OUTPUTS_DIR, "run-manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    print("manifest written: %d inputs, %d outputs" % (len(inputs), len(outputs)))


if __name__ == "__main__":
    main()
