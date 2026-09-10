#!/usr/bin/env bash
# Build the tested tiny-dfr Fn and device-loss fixes. Does not install packages or system files.
set -euo pipefail
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  echo "Usage: $0 [new-build-directory]"
  echo 'Downloads pinned tiny-dfr source and Cargo dependencies, then builds locally.'
  echo 'No system files or services are changed. See docs/FN-LAYER-FIX.md to install.'
  exit 0
fi
if (( $# > 1 )); then
  echo "Usage: $0 [new-build-directory]" >&2
  exit 2
fi
for command in git cargo pkg-config; do
  command -v "$command" >/dev/null || { echo "Missing build tool: $command" >&2; exit 1; }
done
pkg-config --exists libinput libudev cairo freetype2 fontconfig librsvg-2.0
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -n ${1:-} ]]; then
  mkdir -- "$1" # Refuse to overwrite an existing checkout.
  build_dir=$(cd -- "$1" && pwd)
else
  build_dir=$(mktemp -d "${TMPDIR:-/tmp}/tiny-dfr-fn-fix.XXXXXXXX")
fi
revision=eb711c87fcbddda67be3fd5ff45385b139e8fb34
git clone --no-checkout https://github.com/AsahiLinux/tiny-dfr.git "$build_dir/source"
git -C "$build_dir/source" checkout --detach "$revision"
git -C "$build_dir/source" apply --check "$project_dir/patches/tiny-dfr-preserve-fn-layer.patch"
git -C "$build_dir/source" apply "$project_dir/patches/tiny-dfr-preserve-fn-layer.patch"
git -C "$build_dir/source" apply --check "$project_dir/patches/tiny-dfr-handle-device-loss.patch"
git -C "$build_dir/source" apply "$project_dir/patches/tiny-dfr-handle-device-loss.patch"
(cd -- "$build_dir/source" && cargo build --release --locked)
target_dir=${CARGO_TARGET_DIR:-target}
[[ $target_dir == /* ]] || target_dir="$build_dir/source/$target_dir"
printf '\nBuilt: %s/release/tiny-dfr\n' "$target_dir"
printf 'Installation and rollback: %s/docs/FN-LAYER-FIX.md\n' "$project_dir"
