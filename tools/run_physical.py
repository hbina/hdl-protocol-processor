"""Launch the pinned CMOS5L flow with source and tool provenance recorded."""

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from combhdl import compile
from examples.combinational.demo import demo

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "info.yaml",
    "src/config.json",
    "src/pins.sdc",
    "src/project.v",
    "src/combhdl_demo.v",
    "examples/combinational/demo.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes() -> dict[str, str]:
    return {name: sha256(ROOT / name) for name in SOURCES}


def capture(command: list[str], cwd: Path = ROOT) -> str:
    return subprocess.run(
        command, cwd=cwd, check=True, text=True, capture_output=True
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "runs/combhdl_demo")
    parser.add_argument("--engine", choices=("podman", "docker"))
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    record_dir = ROOT / "build/physical" / run_dir.name
    if run_dir.exists() or record_dir.exists():
        parser.error(
            "run or provenance directory already exists; select a fresh --run-dir"
        )
    if (ROOT / "src/combhdl_demo.v").read_text() != compile(demo).verilog:
        parser.error("generated demo is stale; run tools.check_generated --write")
    engine = args.engine or shutil.which("docker") or shutil.which("podman")
    if engine is None:
        parser.error("no container engine; install Docker or rootless Podman first")
    engine_path = shutil.which(engine)
    if engine_path is None:
        parser.error(f"container engine {engine!r} is not installed")
    info = json.loads(capture([engine_path, "info", "--format", "{{json .}}"]))
    uv_command = ["uv", "run", "--locked", "python"]
    try:
        versions = {"librelane": package_version("librelane")}
    except PackageNotFoundError:
        parser.error("LibreLane is not installed; run uv sync --locked")
    version = versions["librelane"]
    if version != "3.1.0.dev3":
        parser.error(f"expected pinned LibreLane 3.1.0.dev3, got {version}")
    pdk_root = ROOT / ".asic-tools/pdk"
    records: dict[str, object] = {
        "design": demo.name,
        "top": "tt_um_combhdl_demo",
        "run_dir": str(run_dir),
        "source_sha256": source_hashes(),
        "git_revision": capture(["git", "rev-parse", "HEAD"]),
        "git_status": capture(["git", "status", "--porcelain"]),
        "pdk_revision": capture(["git", "rev-parse", "HEAD"], pdk_root),
        "tt_revision": capture(["git", "rev-parse", "HEAD"], ROOT / "tt"),
        "physical_versions": versions,
        "python_executable": sys.executable,
        "engine": info,
    }
    record_dir.mkdir(parents=True)
    for name in SOURCES:
        dest = record_dir / "sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    configure = uv_command + ["tt/tt_tool.py", "--create-user-config", "--ihp"]
    subprocess.run(configure, cwd=ROOT, check=True)
    records["configuration_command"] = configure
    config = ROOT / "src/config_merged.json"
    records["merged_config_sha256"] = sha256(config)
    shutil.copyfile(config, record_dir / "config_merged.json")
    image = f"ghcr.io/librelane/librelane:{version}"
    env = dict(
        os.environ,
        LIBRELANE_CONTAINER_ENGINE=engine_path,
        LIBRELANE_IMAGE_OVERRIDE=image,
    )
    command = uv_command + [
        "-m",
        "librelane",
        "--docker-no-tty",
        "--dockerized",
        "--pdk-root",
        str(pdk_root),
        "--pdk",
        "ihp-sg13cmos5l",
        "--manual-pdk",
        "--run-tag",
        run_dir.name,
        "--force-run-dir",
        str(run_dir),
        str(config),
    ]
    records.update({"command": command, "container_image": image, "status": "running"})
    manifest = record_dir / "launch.json"
    manifest.write_text(json.dumps(records, indent=2) + "\n")
    print(f"Provenance: {manifest}", flush=True)
    run_dir.mkdir(parents=True)
    console = record_dir / "console.log"
    print(f"Physical-flow console: {console}", flush=True)
    with console.open("w") as log:
        result = subprocess.run(
            command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
        )
    records.update(
        {
            "returncode": result.returncode,
            "status": "finished" if result.returncode == 0 else "failed",
            "sources_unchanged": source_hashes() == records["source_sha256"],
        }
    )
    inspect = subprocess.run(
        [engine_path, "image", "inspect", image], capture_output=True, text=True
    )
    if inspect.returncode == 0:
        records["container_inspect"] = json.loads(inspect.stdout)
    artifacts = [
        p
        for folder in ("nl", "gds", "def", "sdc", "spef")
        for p in (run_dir / "final" / folder).rglob("*")
        if p.is_file()
    ]
    records["artifact_sha256"] = {
        str(p.relative_to(run_dir)): sha256(p) for p in artifacts
    }
    manifest.write_text(json.dumps(records, indent=2) + "\n")
    if result.returncode:
        raise SystemExit(result.returncode)
    if records["sources_unchanged"] is not True:
        raise SystemExit(
            "sources changed while the physical flow ran; evidence is not current"
        )


if __name__ == "__main__":
    main()
