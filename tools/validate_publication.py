import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen
import zipfile


REPOSITORY = "https://github.com/GTRows/containment-frontier"
MODULE_PATH = "overrides/mods/continuity-frontier-0.5.0-dev.jar"
WORLD_PREFIX = "overrides/saves/continuity_frontier_v1/"
RUNTIME_PARTS = {"playerdata", "stats", "advancements", "backups", "logs", ".env", "session.lock", "minecraftinstance.json"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def safe_path(name):
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name


def validate_repository(root, check_files=True):
    root = Path(root)
    data = read_json(root / "release.json")
    version = data["version"]
    require(re.fullmatch(r"\d+\.\d+\.\d+-beta\.\d+", version), "Invalid beta version")
    filename = f"Containment-Frontier-{version}-CurseForge.zip"
    require(data["client"]["filename"] == filename, "Client filename must match version")
    require(data["repository"] == REPOSITORY and data["release"] == f"{REPOSITORY}/releases/tag/v{version}", "Release version URL mismatch")
    require(data["client"]["download"] == f"{REPOSITORY}/releases/download/v{version}/{filename}", "Invalid download URL")
    require(data["channel"] == "Beta" and data["java"] == 21 and data["minecraft"] == "1.21.1" and data["loader"] == "NeoForge 21.1.265", "Unexpected beta platform")
    require(data["client"]["appManifestEdited"] is False, "Native App manifest must remain unedited")
    require(data["campaignReady"] is False and data["qualifiedRelease"] is False, "This beta does not qualify the full campaign")
    require(data["serverDownloadAvailable"] is False, "Server binary distribution is not approved")
    require(isinstance(data["client"]["bytes"], int) and data["client"]["bytes"] > 0, "Invalid archive size")
    for value in [data["client"]["sha256"], data["customModuleSha256"], data["dependencyLockSha256"], data["worldLockSha256"], *data["presentationAssets"].values()]:
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "Invalid SHA256")
    require(digest((root / "dependencies.json").read_bytes().replace(b"\r\n", b"\n")) == data["dependencyLockSha256"], "Changed dependency lock")
    require(digest((root / "campaign-world.json").read_bytes().replace(b"\r\n", b"\n")) == data["worldLockSha256"], "Changed world lock")
    for name, expected in data["presentationAssets"].items():
        require(safe_path(name) and (root / name).is_file() and digest((root / name).read_bytes()) == expected, f"Changed or missing asset: {name}")
    for path in root.rglob("*.md"):
        if ".git" in path.relative_to(root).parts:
            continue
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            target = target.split(' "', 1)[0].strip("<>")
            if urlsplit(target).scheme or target.startswith("#"):
                continue
            local = (path.parent / unquote(target.split("#", 1)[0])).resolve()
            require(local.is_relative_to(root.resolve()) and local.exists(), f"Broken local link in {path.name}: {target}")
    if check_files:
        for path in root.rglob("*"):
            parts = path.relative_to(root).parts
            if {".git", "__pycache__"}.intersection(parts):
                continue
            require(not RUNTIME_PARTS.intersection(parts) and path.suffix.lower() not in {".jar", ".zip", ".log", ".mca", ".dat"} and not path.name.startswith(".env."), f"Forbidden runtime file: {path.relative_to(root)}")
    return data


def validate_archive(root, archive_path):
    root, archive_path = Path(root), Path(archive_path)
    data = validate_repository(root, check_files=False)
    body = archive_path.read_bytes()
    require(len(body) == data["client"]["bytes"] and digest(body) == data["client"]["sha256"], "Changed archive hash or size")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate archive path")
        require(all(safe_path(name) for name in names), "Unsafe archive path")
        require(not any(RUNTIME_PARTS.intersection(PurePosixPath(name).parts) for name in names), "Archive contains player state or runtime files")
        require(archive.testzip() is None, "Corrupt archive")
        manifest = json.loads(archive.read("manifest.json"))
        require(manifest.get("name") == "Containment Frontier" and manifest.get("version") == data["version"] and manifest.get("manifestType") == "minecraftModpack" and manifest.get("manifestVersion") == 1 and manifest.get("overrides") == "overrides", "Invalid manifest identity or version")
        require(manifest["minecraft"]["version"] == data["minecraft"] and manifest["minecraft"]["modLoaders"] == [{"id": "neoforge-21.1.265", "primary": True}], "Invalid manifest platform")
        dependencies = read_json(root / "dependencies.json")
        key = lambda row: (row["projectID"], row["fileID"], row["required"])
        require(sorted(map(key, manifest["files"])) == sorted(map(key, dependencies)) and len({row["projectID"] for row in manifest["files"]}) == len(manifest["files"]), "Manifest dependencies differ from the pinned lock")
        jars = [name for name in names if name.lower().endswith(".jar")]
        if data["curseforgeCatalogApproved"]:
            require(not jars and any(row["projectID"] == 1778960 for row in manifest["files"]), "Approved module must use its platform reference")
        else:
            require(jars == [MODULE_PATH], "Only the original module JAR may be bundled")
            require(digest(archive.read(MODULE_PATH)) == data["customModuleSha256"], "Original module hash mismatch")
        world = read_json(root / "campaign-world.json")
        actual_world = {name[len(WORLD_PREFIX):]: digest(archive.read(name)) for name in names if name.startswith(WORLD_PREFIX) and not name.endswith("/")}
        require(actual_world == world, "Authored world differs from its canonical lock")
    return data


def validate_pr(pr):
    require(re.fullmatch(r"(?:fix|feat|docs|test|ci|chore)(?:\([a-z0-9_-]+\))?: .{8,120}", pr.get("title", "")), "PR title must use fix/feat/docs/test/ci/chore: followed by a clear summary")
    body = re.sub(r"<!--.*?-->", "", pr.get("body") or "", flags=re.S)
    body = re.sub(r"^\s*[-*] \[[ xX]\].*$", "", body, flags=re.M)
    for heading in ("Summary", "Validation", "Gameplay impact"):
        match = re.search(r"^## " + heading + r"\s*\n(.*?)(?=^## |\Z)", body, flags=re.S | re.M)
        require(match and len(match.group(1).strip()) >= 8, f"PR {heading} needs substantive information")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--event", type=Path)
    args = parser.parse_args()
    data = validate_repository(args.root)
    if args.event:
        validate_pr(read_json(args.event)["pull_request"])
    if args.archive:
        validate_archive(args.root, args.archive)
    if args.download:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / data["client"]["filename"]
            with urlopen(data["client"]["download"], timeout=60) as response:
                path.write_bytes(response.read(data["client"]["bytes"] + 1))
            validate_archive(args.root, path)
    print("Publication checks passed")


if __name__ == "__main__":
    main()
