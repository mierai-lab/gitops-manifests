"""Render what Argo CD renders, for every Application of apps/ whose source is this repository: a kustomize directory
(kubectl kustomize) or a Helm chart with value files (helm template). Used by validate.sh and diff.sh, so both cover
every layout the Applications use.

  python3 scripts/render.py list [root]          one line per Application: <name> <source path>
  python3 scripts/render.py render <name> [root] its manifests (root: another checkout, e.g. the PR's base)

Reads the Application files with regular expressions (they follow apps/*.yaml) and the descriptors with appdesc.py.
"""
import glob
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # appdesc (python3 -I does not add the script's dir)

REPO = "https://github.com/mierai-lab/gitops-manifests.git"


def apps(root="."):
    """Applications listed in apps/*.yaml, then those the ApplicationSet derives from */app.yaml."""
    out = []
    for f in sorted(glob.glob(os.path.join(root, "apps", "*.yaml"))):
        s = open(f).read()
        if not re.search(r"^kind: Application$", s, re.M) or f"repoURL: {REPO}" not in s:  # not the ApplicationSet
            continue
        name = re.search(r"^metadata:\n(?:\s+.*\n)*?\s+name:\s*(\S+)", s, re.M).group(1)
        path = re.search(r"^\s+path:\s*(\S+)", s, re.M).group(1)
        ns = re.search(r"destination:\s*\n(?:\s+\w+:.*\n)*?\s+namespace:\s*(\S+)", s).group(1)
        vf = re.search(r"valueFiles:\s*\[([^\]]*)\]", s)
        rel = re.search(r"releaseName:\s*(\S+)", s)
        out.append({"name": name, "path": path, "namespace": ns,
                    "values": [v.strip() for v in vf.group(1).split(",") if v.strip()] if vf else [],
                    "release": rel.group(1) if rel else name, "enforced": "gitops-platform/policies: enforced" in s})
    import appdesc
    for d in appdesc.all_apps(root):
        out += appdesc.applications(d, root)
    return out


def render(app, root="."):
    d = os.path.join(root, app["path"])
    if os.path.exists(os.path.join(d, "Chart.yaml")):
        cmd = ["helm", "template", app["release"], d, "--namespace", app["namespace"]]
        for v in app["values"]:
            cmd += ["-f", os.path.join(d, v)]
    else:
        cmd = ["kubectl", "kustomize", d]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"{app['name']}: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout


if __name__ == "__main__":
    if sys.argv[1] == "list":
        for a in apps(sys.argv[2] if len(sys.argv) > 2 else "."):
            print(a["name"], a["path"])
    elif sys.argv[1] == "render":
        root = sys.argv[3] if len(sys.argv) > 3 else "."
        found = [a for a in apps(root) if a["name"] == sys.argv[2]]
        if found:
            sys.stdout.write(render(found[0], root))
    else:
        sys.exit("usage: render.py list | render <name> [root]")
