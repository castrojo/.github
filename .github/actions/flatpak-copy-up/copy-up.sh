#!/bin/bash
# Copy Flatpak installations that live in a container image layer into the
# writable layer when overlayfs cannot rename their directories in place.
# See action.yml for the failure this prevents.
set -euo pipefail

read -ra installations <<<"${FLATPAK_INSTALLATIONS:-}"
if [ "${#installations[@]}" -eq 0 ]; then
  installations=(/var/lib/flatpak "${HOME:-/root}/.local/share/flatpak")
fi

# Log the overlay options that decide this, so a runner host change shows in
# the job log.
root_opts=$(awk '$2 == "/" { print $3 "," $4 }' /proc/mounts | tr ',' '\n' |
  grep -E '^(overlay|redirect_dir|index|metacopy|xino)' | paste -sd, - || true)
echo "Root filesystem: ${root_opts:-unknown}"
# Without a redirect_dir mount option, the overlay module default applies.
echo "Kernel: $(uname -r); overlay redirect_dir default: $(cat /sys/module/overlay/parameters/redirect_dir 2>/dev/null || echo unknown)"

# rename(2) without the copy fallback that mv(1) has.
# Exit 0: renamed. Exit 18: EXDEV. Exit 1: any other error.
rename_dir() {
  python3 -c '
import errno, os, sys
try:
    os.rename(sys.argv[1], sys.argv[2])
except OSError as e:
    print(f"rename {sys.argv[1]}: {e}", file=sys.stderr)
    sys.exit(18 if e.errno == errno.EXDEV else 1)
' "$1" "$2"
}

for dir in "${installations[@]}"; do
  [ -d "$dir" ] || continue
  # Any directory that the image ships works as a probe. runtime/ is the parent
  # of the deploys that an update retires.
  probe=""
  for candidate in "$dir/runtime" "$dir/app" "$dir/repo"; do
    if [ -d "$candidate" ]; then
      probe=$candidate
      break
    fi
  done
  if [ -z "$probe" ]; then
    echo "$dir: nothing installed, skipping"
    continue
  fi

  status=0
  rename_dir "$probe" "$probe.rename-probe" 2>/dev/null || status=$?
  case $status in
    0)
      rename_dir "$probe.rename-probe" "$probe"
      echo "$dir: directories rename in place, nothing to do"
      ;;
    18)
      echo "$dir: renaming an image-layer directory fails with EXDEV; copying the installation into the writable layer"
      start=$SECONDS
      # cp -a keeps the hard links between the repo and its deploys, so the
      # copy takes no more space than the original.
      cp -a "$dir" "$dir.copy-up"
      rm -rf "$dir"
      mv "$dir.copy-up" "$dir"
      rename_dir "$probe" "$probe.rename-probe"
      rename_dir "$probe.rename-probe" "$probe"
      echo "$dir: copied $(du -sh "$dir" | cut -f1) in $((SECONDS - start))s; directories now rename in place"
      ;;
    *)
      echo "::error::$dir: the rename probe on $probe failed with an error other than EXDEV"
      exit 1
      ;;
  esac
done
