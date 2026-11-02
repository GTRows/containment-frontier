import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


MODULE = Path(__file__).resolve().parents[1] / "tools/validate_publication.py"


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("validate_publication", MODULE)
        cls.validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.validator)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.module = b"original campaign fixture"
        self.entries = {
            "manifest.json": json.dumps({
                "name": "Containment Frontier", "version": "0.5.0-beta.3",
                "minecraft": {"version": "1.21.1", "modLoaders": [
                    {"id": "neoforge-21.1.265", "primary": True}]},
                "manifestType": "minecraftModpack", "manifestVersion": 1,
                "overrides": "overrides", "files": [
                    {"projectID": 1, "fileID": 2, "required": True}]}).encode(),
            "overrides/mods/continuity-frontier-0.5.0-dev.jar": self.module,
            "overrides/saves/continuity_frontier_v1/level.dat": b"authored world",
        }
        self.archive = self.root / "Containment-Frontier-0.5.0-beta.3-CurseForge.zip"
        self.write_archive()
        dependencies = [{"projectID": 1, "fileID": 2, "required": True}]
        self.write_json("dependencies.json", dependencies)
        self.write_json("campaign-world.json", {
            "level.dat": self.digest(b"authored world")})
        (self.root / "README.md").write_text("[Install](INSTALLATION.md)\n", encoding="utf-8")
        (self.root / "INSTALLATION.md").write_text("Install the beta.\n", encoding="utf-8")
        self.metadata = {
            "version": "0.5.0-beta.3", "channel": "Beta", "minecraft": "1.21.1",
            "loader": "NeoForge 21.1.265", "java": 21,
            "repository": "https://github.com/GTRows/containment-frontier",
            "release": "https://github.com/GTRows/containment-frontier/releases/tag/v0.5.0-beta.3",
            "client": {"filename": self.archive.name,
                "sha256": self.digest(self.archive.read_bytes()),
                "bytes": self.archive.stat().st_size,
                "download": "https://github.com/GTRows/containment-frontier/releases/download/v0.5.0-beta.3/" + self.archive.name,
                "appManifestEdited": False},
            "customModuleSha256": self.digest(self.module),
            "curseforgeCatalogApproved": False, "campaignReady": False,
            "qualifiedRelease": False, "serverDownloadAvailable": False,
            "dependencyLockSha256": self.digest((self.root / "dependencies.json").read_bytes()),
            "worldLockSha256": self.digest((self.root / "campaign-world.json").read_bytes()),
            "presentationAssets": {},
        }
        self.save_metadata()

    @staticmethod
    def digest(body):
        return hashlib.sha256(body).hexdigest()

    def write_json(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding="utf-8")

    def save_metadata(self):
        self.write_json("release.json", self.metadata)

    def write_archive(self):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for name, body in self.entries.items():
                archive.writestr(name, body)
        if hasattr(self, "metadata"):
            self.metadata["client"]["sha256"] = self.digest(self.archive.read_bytes())
            self.metadata["client"]["bytes"] = self.archive.stat().st_size
            self.save_metadata()

    def test_valid_repository_and_archive(self):
        self.archive.unlink()
        self.validator.validate_repository(self.root)
        self.write_archive()
        self.validator.validate_archive(self.root, self.archive)

    def test_version_must_match_filename_and_release(self):
        self.metadata["version"] = "0.5.0-beta.4"
        self.save_metadata()
        with self.assertRaisesRegex(ValueError, "version"):
            self.validator.validate_repository(self.root, check_files=False)

    def test_download_must_use_exact_repository_and_version(self):
        self.metadata["client"]["download"] = "https://example.com/pack.zip"
        self.save_metadata()
        with self.assertRaisesRegex(ValueError, "download"):
            self.validator.validate_repository(self.root, check_files=False)

    def test_sha256_format_is_required(self):
        self.metadata["customModuleSha256"] = "not-a-hash"
        self.save_metadata()
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.validator.validate_repository(self.root, check_files=False)

    def test_broken_local_documentation_link_is_rejected(self):
        (self.root / "README.md").write_text("[Missing](MISSING.md)\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "local link"):
            self.validator.validate_repository(self.root, check_files=False)

    def test_dependency_lock_changes_require_new_hash(self):
        self.write_json("dependencies.json", [])
        with self.assertRaisesRegex(ValueError, "dependency lock"):
            self.validator.validate_repository(self.root, check_files=False)

    def test_lock_hashes_are_portable_across_windows_and_linux(self):
        for name, field in [("dependencies.json", "dependencyLockSha256"),
                            ("campaign-world.json", "worldLockSha256")]:
            body = (json.dumps(json.loads((self.root / name).read_text()), indent=2) + "\n").encode()
            self.metadata[field] = self.digest(body)
            (self.root / name).write_bytes(body.replace(b"\n", b"\r\n"))
        self.save_metadata()
        self.validator.validate_repository(self.root, check_files=False)

    def test_original_asset_hash_is_checked(self):
        self.metadata["presentationAssets"] = {"icon.png": self.digest(b"original")}
        (self.root / "icon.png").write_bytes(b"changed")
        self.save_metadata()
        with self.assertRaisesRegex(ValueError, "asset"):
            self.validator.validate_repository(self.root, check_files=False)

    def test_runtime_files_do_not_belong_in_repository(self):
        with self.assertRaisesRegex(ValueError, "runtime"):
            self.validator.validate_repository(self.root)

    def test_corrupt_archive_hash_is_rejected(self):
        self.archive.write_bytes(self.archive.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "archive"):
            self.validator.validate_archive(self.root, self.archive)

    def test_manifest_version_mismatch_is_rejected(self):
        manifest = json.loads(self.entries["manifest.json"])
        manifest["version"] = "0.5.0-beta.2"
        self.entries["manifest.json"] = json.dumps(manifest).encode()
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.validator.validate_archive(self.root, self.archive)

    def test_module_must_match_tested_hash(self):
        self.entries["overrides/mods/continuity-frontier-0.5.0-dev.jar"] = b"different module"
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "module"):
            self.validator.validate_archive(self.root, self.archive)

    def test_third_party_jar_cannot_be_bundled(self):
        self.entries["overrides/mods/third-party.jar"] = b"third party"
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "JAR"):
            self.validator.validate_archive(self.root, self.archive)

    def test_path_traversal_is_rejected(self):
        self.entries["overrides/../escape.txt"] = b"bad path"
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "path"):
            self.validator.validate_archive(self.root, self.archive)

    def test_player_state_is_rejected(self):
        self.entries["overrides/saves/continuity_frontier_v1/playerdata/player.dat"] = b"player"
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "player"):
            self.validator.validate_archive(self.root, self.archive)

    def test_authored_world_cannot_change_silently(self):
        self.entries["overrides/saves/continuity_frontier_v1/level.dat"] = b"new world"
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "world"):
            self.validator.validate_archive(self.root, self.archive)

    def test_dependencies_must_match_lock(self):
        manifest = json.loads(self.entries["manifest.json"])
        manifest["files"][0]["fileID"] = 9
        self.entries["manifest.json"] = json.dumps(manifest).encode()
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "dependencies"):
            self.validator.validate_archive(self.root, self.archive)

    def test_duplicate_dependency_is_rejected(self):
        manifest = json.loads(self.entries["manifest.json"])
        manifest["files"] *= 2
        self.entries["manifest.json"] = json.dumps(manifest).encode()
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "dependencies"):
            self.validator.validate_archive(self.root, self.archive)

    def test_complete_pr_is_accepted_as_data(self):
        self.validator.validate_pr({"title": "fix: correct installation instructions",
            "body": "## Summary\nCorrect a broken link.\n## Validation\npython tools/validate_publication.py\n## Gameplay impact\nNone; documentation only.\n"})

    def test_pr_requires_allowed_title_prefix(self):
        with self.assertRaisesRegex(ValueError, "title"):
            self.validator.validate_pr({"title": "update", "body": ""})

    def test_pr_requires_actual_validation_evidence(self):
        with self.assertRaisesRegex(ValueError, "Validation"):
            self.validator.validate_pr({"title": "docs: update installation", "body":
                "## Summary\nUpdate docs.\n## Validation\n<!-- commands and results -->\n## Gameplay impact\nNone.\n"})

    def test_template_checkboxes_are_not_gameplay_evidence(self):
        with self.assertRaisesRegex(ValueError, "Gameplay impact"):
            self.validator.validate_pr({"title": "docs: update installation", "body":
                "## Summary\nCorrect install steps.\n## Validation\nPublic tests pass.\n## Gameplay impact\n<!-- explain impact -->\n- [ ] I ran tests and excluded runtime files.\n"})


if __name__ == "__main__":
    unittest.main()
