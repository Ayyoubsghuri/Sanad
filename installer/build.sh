#!/usr/bin/env bash
# Builds the two Windows installers of Sanad on Linux (also what the GitHub workflow runs):
#     installer/out/SanadSetup-<version>.exe   (NSIS)        installer/out/Sanad-<version>.msi   (WiX, built with wixl)
# Needs: node + npm, python3, curl, unzip, makensis (apt: nsis), wixl (apt: wixl).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
version="${1:-$(sed -n 's/^version = "\(.*\)"/\1/p' "$root/backend/pyproject.toml")}"
uv_version="${UV_VERSION:-latest}"   # pin with UV_VERSION=0.x.y
stage="$here/stage"
out="$here/out"
rm -rf "$stage" "$out"
mkdir -p "$stage/bin" "$stage/backend" "$out"

echo "== frontend"
(cd "$root/frontend" && { [ -d node_modules ] || npm ci --legacy-peer-deps; } && npm run build)
cp -r "$root/frontend/dist" "$stage/frontend"
rm -rf "$stage/frontend/assets/aistudio"   # design references of the prototype, not used by the app

echo "== backend"
cp -r "$root/backend/legalrag" "$root/backend/tools" "$stage/backend/"
cp "$root/backend/pyproject.toml" "$root/backend/README.md" "$root/backend/pack_release.json" "$stage/backend/"
find "$stage" -name __pycache__ -type d -prune -exec rm -rf {} +
cp "$here/Start-Sanad.ps1" "$here/Setup-Sanad.ps1" "$here/sanad.ico" "$stage/"

echo "== uv $uv_version (installs Python and the packages on the user's machine)"
if [ -n "${UV_EXE:-}" ]; then
  cp "$UV_EXE" "$stage/bin/uv.exe"
else
  tmp="$(mktemp -d)"
  base="https://github.com/astral-sh/uv/releases"
  [ "$uv_version" = latest ] && url="$base/latest/download" || url="$base/download/$uv_version"
  curl -fsSL --retry 3 -o "$tmp/uv.zip" "$url/uv-x86_64-pc-windows-msvc.zip"
  unzip -q -j "$tmp/uv.zip" uv.exe -d "$stage/bin"
  rm -rf "$tmp"
fi

echo "== SanadSetup-$version.exe"
makensis -V2 -DVERSION="$version" -DSTAGE="$stage" -DOUT="$out/SanadSetup-$version.exe" "$here/sanad.nsi"

echo "== Sanad-$version.msi"
python3 "$here/gen_wxs.py" "$stage" "$version" > "$here/sanad.wxs"
wixl -a x64 -o "$out/Sanad-$version.msi" "$here/sanad.wxs"

(cd "$out" && sha256sum ./* > SHA256SUMS.txt && cat SHA256SUMS.txt)
