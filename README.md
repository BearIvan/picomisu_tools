<p align="center"><img src="logo/picomisu.png" alt="Picomisu" width="320"></p>

# picomisu_tools

These are the host tools of [Picomisu](https://github.com/BearIvan/picomisu), the system image
for the PICO 4 Pro. They turn the output of the Android build into an image you can install on
the headset, and they install it. `repo sync` checks this repository out at `picomisu/` in the
Picomisu tree.

**The build and install guide is in the [manifest README](https://github.com/BearIvan/picomisu#readme).**
To build:

```bash
picomisu/build.sh
```

## Main tools

| Path | Purpose |
|---|---|
| `build.sh` | Builds the release with one command: factory firmware, factory files, `make`, release image and checks |
| `build/build-caf.sh` | Sets up the CAF build environment (`lunch aosp_pico4pro-*`, `make`) |
| `config/stock-firmware.lock.json` | URL and SHA-256 of the factory PICO OS 5.13.7 OTA and its images |
| `tools/prepare-stock.py`, `tools/extract-stock.py` | Download the pinned OTA and reconstruct the factory partition images |
| `tools/prepare-host-compat.py` | Provides `libncurses5`/`libtinfo5` for the prebuilt Clang, without installing them |
| `tools/extract-vr-system.py` | Unpacks the factory system, vendor, product and odm trees (read-only) |
| `tools/inspect-factory-apks.py`, `tools/inspect-additional-apks.py` | Factory APK identities and signers |
| `tools/assemble-source-image.py` | Release image: merge with factory components, re-sign, generate files, ext4, AVB, readback |
| `tools/check-source-image.py` | Offline checks: SELinux labels, init, native dependencies, VINTF, class path |
| `tools/source-ota.py` | Installation, OTA deltas and updates, switching back to factory |
| `tools/prepare-updater-recovery.py` | The updater recovery that writes `system` |
| `tools/picomisu_env.py` | Paths used by the release pipeline (see below) |

The other scripts in `tools/` and the documents in `docs/research/` are the research and audit
work behind the port: comparisons with the factory image, ABI and API parity, and wire fixtures.
The build does not need them.

## Paths

`tools/picomisu_env.py` works out where everything is:

- **Repo tree.** When this repository sits at `TOP/picomisu`, the tools use `TOP` as the
  source tree. Build output goes to `OUT_DIR` (default `TOP/out`), and factory images, staging
  and outputs go to `PICOMISU_WORK` (default `out/picomisu`).
- **Legacy workspace.** Otherwise the tools use the author's original fixed workspace on a
  dedicated ext4 volume, so older trees keep building unchanged.

## Factory files

This repository holds no PICO factory binaries. The release pipeline reads the factory images
reconstructed from the pinned OTA and checks them against `config/stock-firmware.lock.json`.

## License

[GNU General Public License v3.0](LICENSE). `tools/third_party/avb` (avbtool from AOSP) keeps its
MIT license.
