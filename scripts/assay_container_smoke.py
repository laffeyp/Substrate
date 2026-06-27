"""Live smoke of the container backend on flask-4045: env works, network is OFF (lockdown), an edit lands
in /testbed, the in-container diff captures it, and the baseline (pre-edit) diff is clean. Env-gated."""

import sys

from substrate.assay.swebench_container import ContainerWorkspace

IID = "pallets__flask-4045"


def main() -> None:
    with ContainerWorkspace(IID) as ws:
        print("container up. checks:", flush=True)

        rc, ver = ws.exec("python -c 'import flask; print(flask.__version__)'")
        print(f"  env: rc={rc} flask={ver.strip()!r} (deps installed in the image)", flush=True)

        _, net = ws.exec("curl -sS --max-time 5 https://pypi.org >/dev/null 2>&1 && echo HAS_NET || echo NO_NET")
        print(f"  network: {net.strip()} (expect NO_NET — --network none lockdown)", flush=True)

        baseline = ws.diff()
        print(f"  baseline diff length: {len(baseline)} (expect ~0 — clean /testbed, no build-artifact noise)", flush=True)

        src = ws.read_file("src/flask/blueprints.py")
        print(f"  read src/flask/blueprints.py: {len(src)} chars (expect >0)", flush=True)

        ws.write_file("src/flask/blueprints.py", src + "\n# smoke-edit\n")
        patch = ws.diff()
        ok = "# smoke-edit" in patch and "src/flask/blueprints.py" in patch
        print(f"  after edit, diff captures it: {ok} ({len(patch)}b)", flush=True)

        passed = rc == 0 and "NO_NET" in net and len(baseline) == 0 and ok
        print(f"\n=== CONTAINER SMOKE: {'PASS' if passed else 'FAIL'} ===", flush=True)
        sys.exit(0 if passed else 3)


if __name__ == "__main__":
    main()
