# Galaxy Buds On — experimental macOS diagnostic build

This repository builds a **read-only, experimental Galaxy Buds On (SM-U600)** variant of [GalaxyBudsClient](https://github.com/timschneeb/GalaxyBudsClient) in GitHub Actions. It is a compatibility investigation, **not a working multipoint unlock**.

## Build and download

1. Open the [Actions tab](https://github.com/matt-gummow/galaxy-buds-on-preview/actions) and select **Build Galaxy Buds On diagnostic app (macOS)**.
2. Open the latest successful run. If no run appears, click **Run workflow**.
3. Under **Artifacts**, download **GalaxyBudsOn-diagnostic-macos-arm64**.
4. Unzip the downloaded artifact and install the included macOS Apple Silicon `.pkg`.
5. The installer is unsigned. Only allow it in macOS Privacy & Security if you trust this repo and its upstream source.

No local Xcode installation or Apple App Store sign-in is needed. The cloud workflow checks out upstream commit `85dfc8bb39fc45d3c30ecf71ab2c663fb1d41729`, applies `add_buds_on.py`, compiles the macOS native Bluetooth library, and publishes a `.pkg` with .NET 11.

## Scope of this preview

- Tries to identify Galaxy Buds On by the advertised Bluetooth name.
- Uses an *unverified* Galaxy Buds management service UUID. Bluetooth audio pairing alone does not establish that this service is present.
- Blocks **all outgoing normal and alternative Samsung protocol messages** on this experimental model, including configuration, firmware operations, and multipoint writes.
- Does not decode incoming frames as if they belonged to an older Galaxy Buds model.
- Enables optional raw receive diagnostics only when the app starts with environment variable `GALAXYBUDS_ON_LOG_RAW=1`.

The raw receive logs may contain device identifiers or other sensitive metadata. Do not post unredacted logs publicly. Consider disabling optional application crash reporting and crowdsourcing before tests.

**Next step:** Validate the actual Buds On Bluetooth service characteristics and traffic from a connected Mac. Once verified, model-specific functionality can be implemented incrementally. Do **not** send the existing Galaxy Buds2 Pro multipoint commands to Buds On without testing the protocol first.

## Important limits

A successful CI build does not prove that the package installs, recognizes Buds On, communicates over Bluetooth, or enables multipoint. The macOS package is unsigned and may need manual approval. Builds are hosted on GitHub-hosted macOS runners; access and quotas depend on GitHub's current policies.

If the run fails, open the failed step in the GitHub Actions log and inspect the error.
