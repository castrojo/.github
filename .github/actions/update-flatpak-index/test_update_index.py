#!/usr/bin/env python3
"""Unit and fixture tests for the update-flatpak-index action script."""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("update-index.py")
_SPEC = importlib.util.spec_from_file_location("update_index", SCRIPT)
update_index = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(update_index)


REQUIRED_LABELS = {
    "org.flatpak.ref": "app/org.example.App/x86_64/stable",
    "org.flatpak.metadata": "metadata",
}
APPSTREAM_LABELS = {
    "org.freedesktop.appstream.appdata": "appdata",
    "org.freedesktop.appstream.icon-64": "icon-64",
    "org.freedesktop.appstream.icon-128": "icon-128",
}


class UpdateIndexTests(unittest.TestCase):
    def write_oci_layout(self, root, labels=None, architecture="x86_64"):
        labels = labels if labels is not None else {**REQUIRED_LABELS, **APPSTREAM_LABELS}
        oci_dir = Path(root) / "oci"
        blobs = oci_dir / "blobs" / "sha256"
        blobs.mkdir(parents=True)

        manifest_digest = "sha256:" + "1" * 64
        config_digest = "sha256:" + "2" * 64
        (oci_dir / "index.json").write_text(
            json.dumps({"manifests": [{"digest": manifest_digest}]}), encoding="utf-8"
        )
        (blobs / manifest_digest.split(":", 1)[1]).write_text(
            json.dumps({"config": {"digest": config_digest}}), encoding="utf-8"
        )
        (blobs / config_digest.split(":", 1)[1]).write_text(
            json.dumps(
                {
                    "architecture": architecture,
                    "config": {"Labels": labels},
                }
            ),
            encoding="utf-8",
        )
        return oci_dir, manifest_digest

    def test_read_oci_layout_resolves_manifest_and_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            oci_dir, manifest_digest = self.write_oci_layout(temp_dir)

            actual_digest, config = update_index.read_oci_layout(oci_dir)

        self.assertEqual(actual_digest, manifest_digest)
        self.assertEqual(config["architecture"], "x86_64")
        self.assertEqual(
            config["config"]["Labels"],
            {**REQUIRED_LABELS, **APPSTREAM_LABELS},
        )

    def test_read_oci_layout_rejects_missing_or_empty_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(FileNotFoundError, "index.json not found"):
                update_index.read_oci_layout(Path(temp_dir) / "missing")

            oci_dir = Path(temp_dir) / "empty"
            oci_dir.mkdir()
            (oci_dir / "index.json").write_text(
                json.dumps({"manifests": []}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "No manifests listed"):
                update_index.read_oci_layout(oci_dir)

    def test_read_oci_layout_rejects_missing_manifest_or_config_blob(self):
        for digest_char in ("1", "2"):
            with self.subTest(blob=digest_char), tempfile.TemporaryDirectory() as temp_dir:
                oci_dir, _ = self.write_oci_layout(temp_dir)
                (oci_dir / "blobs" / "sha256" / (digest_char * 64)).unlink()
                with self.assertRaises(FileNotFoundError):
                    update_index.read_oci_layout(oci_dir)

    def test_filter_labels_keeps_flatpak_and_appstream_contract(self):
        labels = {
            **REQUIRED_LABELS,
            **APPSTREAM_LABELS,
            "com.example.internal": "drop-me",
        }

        self.assertEqual(
            update_index.filter_labels(labels),
            {**REQUIRED_LABELS, **APPSTREAM_LABELS},
        )
        self.assertEqual(update_index.filter_labels(None), {})

    def test_build_image_entry_requires_flatpak_labels(self):
        for name in REQUIRED_LABELS:
            with self.subTest(label=name):
                labels = {**REQUIRED_LABELS, **APPSTREAM_LABELS}
                del labels[name]
                with self.assertRaisesRegex(ValueError, name):
                    update_index.build_image_entry(
                        "sha256:" + "1" * 64,
                        {"config": {"Labels": labels}},
                        ["latest"],
                        False,
                    )

    def test_build_image_entry_warns_for_optional_appstream_metadata(self):
        labels = dict(REQUIRED_LABELS)
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            entry = update_index.build_image_entry(
                "sha256:" + "1" * 64,
                {"config": {"Labels": labels}},
                ["latest"],
                False,
            )

        self.assertIn("No AppStream metadata", stderr.getvalue())
        self.assertEqual(entry["Architecture"], "amd64")
        self.assertEqual(entry["OS"], "linux")
        self.assertEqual(entry["Labels"], labels)

    def test_build_image_entry_can_require_appstream_metadata(self):
        for name in APPSTREAM_LABELS:
            with self.subTest(label=name):
                labels = {**REQUIRED_LABELS, **APPSTREAM_LABELS}
                del labels[name]
                with self.assertRaisesRegex(ValueError, "No AppStream metadata"):
                    update_index.build_image_entry(
                        "sha256:" + "1" * 64,
                        {"config": {"Labels": labels}},
                        ["latest"],
                        True,
                    )

    def test_merge_entry_replaces_same_architecture_and_application_only(self):
        old_app = {
            "Architecture": "x86_64",
            "Labels": {"org.flatpak.ref": "app/old"},
            "Digest": "old",
        }
        other_arch = {
            "Architecture": "aarch64",
            "Labels": {"org.flatpak.ref": "app/old"},
            "Digest": "arm",
        }
        other_app = {
            "Architecture": "x86_64",
            "Labels": {"org.flatpak.ref": "app/other"},
            "Digest": "other",
        }
        index = {
            "Results": [
                {
                    "Name": "tuna-os/example",
                    "Images": [old_app, other_arch, other_app],
                }
            ]
        }
        replacement = {
            "Architecture": "x86_64",
            "Labels": {"org.flatpak.ref": "app/old"},
            "Digest": "new",
        }

        update_index.merge_entry(index, "tuna-os/example", replacement)

        images = index["Results"][0]["Images"]
        self.assertEqual([image["Digest"] for image in images], ["arm", "other", "new"])

    def test_merge_entry_adds_and_sorts_new_repository(self):
        index = {"Results": [{"Name": "z-repo", "Images": []}]}
        image = {
            "Architecture": "x86_64",
            "Labels": {"org.flatpak.ref": "app/example"},
            "Digest": "digest",
        }

        update_index.merge_entry(index, "a-repo", image)

        self.assertEqual(
            [result["Name"] for result in index["Results"]],
            ["a-repo", "z-repo"],
        )
        self.assertEqual(index["Results"][0]["Images"], [image])

    def test_main_creates_index_with_registry_and_persisted_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            oci_dir, manifest_digest = self.write_oci_layout(temp_dir)
            index_file = Path(temp_dir) / "index" / "static"
            argv = [
                "update-index.py",
                "--oci-dir",
                str(oci_dir),
                "--index-file",
                str(index_file),
                "--repo-name",
                "tuna-os/example",
                "--registry",
                "registry.example",
                "--tags",
                "latest",
                "stable",
            ]

            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                update_index.main()

            index = json.loads(index_file.read_text(encoding="utf-8"))

        self.assertEqual(index["Registry"], "https://registry.example")
        self.assertEqual(index["Results"][0]["Name"], "tuna-os/example")
        image = index["Results"][0]["Images"][0]
        self.assertEqual(image["Digest"], manifest_digest)
        self.assertEqual(image["Tags"], ["latest", "stable"])
        self.assertEqual(image["Labels"], {**REQUIRED_LABELS, **APPSTREAM_LABELS})

    def run_cli(self, root, oci_dir, *extra_args):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT.resolve()),
                "--oci-dir", str(oci_dir),
                "--repo-name", "tuna-os/example",
                *extra_args,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_defaults_and_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            oci_dir, manifest_digest = self.write_oci_layout(temp_dir)
            result = self.run_cli(temp_dir, oci_dir, "--require-appstream")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                result.stdout,
                "Updated index/static: tuna-os/example (x86_64), appstream=yes\n",
            )
            content = (Path(temp_dir) / "index" / "static").read_text()
            self.assertTrue(content.endswith("\n"))
            index = json.loads(content)
            self.assertEqual(index["Registry"], "https://ghcr.io")
            image = index["Results"][0]["Images"][0]
            self.assertEqual(image["Digest"], manifest_digest)
            self.assertEqual(image["Tags"], ["latest"])

    def test_cli_updates_existing_index_and_preserves_other_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            oci_dir, _ = self.write_oci_layout(temp_dir)
            result = self.run_cli(temp_dir, oci_dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            index_file = Path(temp_dir) / "index" / "static"
            index = json.loads(index_file.read_text())
            index["Registry"] = "https://existing.example"
            other_repo = {"Name": "z-repo", "Images": []}
            index["Results"].append(other_repo)
            old_image = index["Results"][0]["Images"][0]
            old_image["Digest"] = "sha256:old"
            other_arch = {**old_image, "Architecture": "aarch64"}
            other_app = {
                **old_image,
                "Labels": {"org.flatpak.ref": "app/org.example.Other/x86_64/stable"},
            }
            index["Results"][0]["Images"].extend([other_arch, other_app])
            index_file.write_text(json.dumps(index))

            result = self.run_cli(temp_dir, oci_dir, "--tags", "stable", "v1")
            self.assertEqual(result.returncode, 0, result.stderr)
            updated = json.loads(index_file.read_text())
            self.assertEqual(updated["Registry"], "https://existing.example")
            self.assertEqual(updated["Results"][1], other_repo)
            images = updated["Results"][0]["Images"]
            self.assertEqual(images[:2], [other_arch, other_app])
            self.assertEqual(len(images), 3)
            self.assertEqual(images[2]["Tags"], ["stable", "v1"])
            self.assertEqual(images[2]["Digest"], "sha256:" + "1" * 64)

    def test_cli_appstream_warning_and_strict_failure_leave_index_intact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            oci_dir, _ = self.write_oci_layout(temp_dir, labels=REQUIRED_LABELS)
            result = self.run_cli(temp_dir, oci_dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WARNING: No AppStream metadata", result.stderr)
            self.assertIn("appstream=no", result.stdout)
            index_file = Path(temp_dir) / "index" / "static"
            original = index_file.read_bytes()

            result = self.run_cli(temp_dir, oci_dir, "--require-appstream")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No AppStream metadata", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(index_file.read_bytes(), original)
            index_file.unlink()
            result = self.run_cli(temp_dir, oci_dir, "--require-appstream")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(index_file.exists())


class PublishFlatpakIndexActionTests(unittest.TestCase):
    """Run publish-flatpak-index's script against a local docs-repo."""

    ACTION = Path(__file__).resolve().parent.parent / "publish-flatpak-index" / "action.yml"
    REMOTE = "git@github.com:example/docs.git"

    def git(self, env, *args, cwd=None):
        return subprocess.run(
            ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
        ).stdout

    def test_index_commit_names_its_source_run(self):
        import yaml  # update-index.py itself needs only the standard library

        action = yaml.safe_load(self.ACTION.read_text(encoding="utf-8"))
        script = action["runs"]["steps"][0]["run"]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            oci_dir, _ = UpdateIndexTests.write_oci_layout(self, root)
            docs_repo = root / "docs.git"
            env = {
                "PATH": os.environ["PATH"],
                "HOME": str(root),
                "GIT_CONFIG_NOSYSTEM": "1",
                # Serve the docs-repo remote from a local bare repository.
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": f"url.{docs_repo.as_uri()}.insteadOf",
                "GIT_CONFIG_VALUE_0": self.REMOTE,
            }
            self.git(env, "init", "-q", "--bare", "-b", "main", str(docs_repo))
            seed = root / "seed"
            self.git(env, "clone", "-q", self.REMOTE, str(seed))
            (seed / "static" / "flatpak" / "index").mkdir(parents=True)
            (seed / "static" / "flatpak" / "index" / "static").write_text("{}\n")
            self.git(env, "add", "-A", cwd=seed)
            self.git(env, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                     "commit", "-q", "-m", "seed", cwd=seed)
            self.git(env, "push", "-q", "origin", "HEAD:main", cwd=seed)

            run_env = {
                **env,
                "ACTION_PATH": str(self.ACTION.parent),
                "OCI_DIR": str(oci_dir),
                "INDEX_FILE": "static/flatpak/index/static",
                "REPO_NAME": "tuna-os/example",
                "REGISTRY": "ghcr.io",
                "TAGS": "latest",
                "DOCS_REPO": "example/docs",
                "FLATPAK_INDEX_SSH_KEY": "not-a-key",
                "FLATPAK_INDEX_TOKEN": "",
                "MAX_ATTEMPTS": "1",
                "GITHUB_REPOSITORY": "tuna-os/example",
                "GITHUB_WORKFLOW_REF": "tuna-os/example/.github/workflows/release.yml@refs/tags/v1",
                "GITHUB_SERVER_URL": "https://github.com",
                "GITHUB_RUN_ID": "42",
                "GITHUB_RUN_ATTEMPT": "2",
            }
            result = subprocess.run(
                ["bash", "-c", script], env=run_env, capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            message = self.git(env, "--git-dir", str(docs_repo), "log", "-1", "--format=%B", "main")

        self.assertEqual(
            message.strip().splitlines(),
            [
                "chore(flatpak): update tuna-os/example OCI index",
                "",
                "Source-Repository: tuna-os/example",
                "Source-Workflow: tuna-os/example/.github/workflows/release.yml@refs/tags/v1",
                "Source-Run: https://github.com/tuna-os/example/actions/runs/42/attempts/2",
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
