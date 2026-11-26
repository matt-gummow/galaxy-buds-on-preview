"""Inspect the public Galaxy Connect package without installing or starting it."""
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

PRODUCT = "9NGW9K44GQ5F"
IDENTITY = "SAMSUNGELECTRONICSCoLtd.SamsungContinuityService"
FAMILY = IDENTITY + "_wyx1vj98g3asy"
LIMIT = 500 * 1024 * 1024
TOKENS = ("SM-U600", "SM-R640", "SM-U600N", "Galaxy Buds On", "Galaxy Buds4 Pro",
          "AutoSwitchBuds", "BudsAutoSwitch", "BudsBLEAdvertisementBackgroundTask",
          "AutoSwitchBudsVM", "EasyConnect2", "ModuleEasyConnect", "DllBudsMsgFmt",
          "GalaxyBudsOn", "BudsOnDevice", "BluetoothLEAudio", "BluetoothLEAdvertisementWatcher",
          "MDE_VERSION", "ContinuityFeatureApps", "Windows.Media.Audio", "BluetoothClassicDevice")
NEEDLES = {t: (t.lower().encode(), t.lower().encode("utf-16le")) for t in TOKENS}


def report(line):
    print(line, flush=True)


def fetch_json(url, body=None):
    request = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=55) as response:
        return json.load(response)


def public_download(p, tmp):
    # WinGet uses these same Microsoft Store SFS calls to request public package files.
    service = "https://storeapps.api.cdp.microsoft.com/api/v2/contents/storeapps/namespaces/default/names/"
    category = p["FulfillmentData"]["WuCategoryId"]
    stem = service + urllib.parse.quote(category, safe="") + "/versions/"
    data = fetch_json(stem + "latest?action=select", b'{"TargetingAttributes":{}}')
    if data["ContentId"]["Name"].lower() != category.lower():
        raise ValueError("Unexpected SFS identity")
    version = urllib.parse.quote(data["ContentId"]["Version"], safe="")
    files = fetch_json(stem + version + "/files?action=GenerateDownloadInfo", b"")
    valid = []
    for f in files:
        moniker = f["FileMoniker"].lower()
        ext = Path(f["FileId"]).suffix.lower()
        if not moniker.startswith(IDENTITY.lower() + "_") or "wyx1vj98g3asy" not in moniker:
            continue
        arch = [s.lower() for s in f["ApplicabilityDetails"]["Architectures"]]
        if arch and not set(arch).intersection({"amd64", "x64", "none", "neutral"}):
            continue
        if ext not in (".msixbundle", ".appxbundle", ".appx", ".msix"):
            continue
        if not 0 < f["SizeInBytes"] <= LIMIT:
            continue
        valid.append((ext in (".msixbundle", ".appxbundle"), "_x64_" in moniker, f["SizeInBytes"], f))
    if not valid:
        raise ValueError("No public package matching the requested architecture")
    f = max(valid, key=lambda item: item[:3])[-1]
    parsed = urllib.parse.urlsplit(f["Url"])
    if parsed.scheme not in ("http","https") or not (parsed.hostname or "").endswith((".delivery.mp.microsoft.com", ".dl.delivery.mp.microsoft.com", ".windowsupdate.com")):
        raise ValueError("Unexpected package download origin")
    url = parsed._replace(scheme="https").geturl()
    path = tmp / ("GalaxyConnect" + Path(f["FileId"]).suffix)
    expected = f["Hashes"]["Sha256"]
    expected = bytes.fromhex(expected) if re.fullmatch(r"[0-9A-Fa-f]{64}", expected) else base64.b64decode(expected, validate=True)
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=100) as response, path.open("wb") as output:
        if not response.geturl().startswith("https://"):
            raise ValueError("HTTPS delivery required")
        for block in iter(lambda: response.read(1024 * 1024), b""):
            if output.tell() + len(block) > f["SizeInBytes"]:
                raise ValueError("Store file length limit exceeded")
            output.write(block)
            digest.update(block)
    if path.stat().st_size != f["SizeInBytes"] or digest.digest() != expected:
        raise ValueError("Store hash or length mismatch")
    return path


def read_x64(archive, out):
    if "AppxManifest.xml" in archive.namelist():
        inspect_package(archive, out)
        return
    root = ET.fromstring(archive.read("AppxMetadata/AppxBundleManifest.xml"))
    packages = [p for p in root.iter() if p.tag.split("}")[-1] == "Package" and p.get("Type", "").lower() == "application" and p.get("Architecture","").lower() in ("x64","neutral")]
    packages.sort(key=lambda p: p.get("Architecture") != "x64")
    if not packages:
        raise ValueError("No x64 application in bundle")
    selected = archive.getinfo(packages[0].attrib["FileName"])
    if selected.file_size > LIMIT:
        raise ValueError("Nested application exceeds size limit")
    with ZipFile(io.BytesIO(archive.read(selected))) as nested:
        inspect_package(nested, out)


def inspect_package(archive, out):
    root = ET.fromstring(archive.read("AppxManifest.xml"))
    identity = next(x for x in root if x.tag.split("}")[-1] == "Identity")
    if identity.get("Name") != IDENTITY:
        raise ValueError("Unexpected inner package name")
    out.append(f'Inspected {identity.get("Name")} {identity.get("Version")} ({identity.get("ProcessorArchitecture")}).')
    modules = []
    filemarks = []
    packed = []
    containers = []
    for entry in archive.infolist():
        name = PurePosixPath(entry.filename).name
        if not re.fullmatch(r"[\w .()+~-]{1,145}", name):
            continue
        suffix = Path(name).suffix.lower()
        if suffix in (".exe", ".dll", ".winmd", ".pri", ".sys", ".json", ".xml", ".dat", ".ini", ".config", ".db", ".txt", ".bin"):
            if suffix in (".exe", ".dll", ".winmd", ".sys") and re.search(r"buds|connect|switch|mcf|continuity|handoff|audio|bleadver", name, re.I):
                modules.append(name)
            if 0 < entry.file_size <= 150 * 1024 * 1024:
                body = archive.read(entry).lower()
                hits = [t for t, variants in NEEDLES.items() if any(n in body for n in variants)]
                if hits:
                    filemarks.append((name, hits))
        elif suffix in (".cab", ".msi", ".zip", ".7z", ".msix", ".appx"):
            containers.append(name)
    out.append("Named components: " + ", ".join(sorted(set(modules))[:90]))
    out.append("Nested containers left uninspected: " + (", ".join(sorted(set(containers))[:35]) or "none"))
    out.append("Static literal matches (co-occurrence doesn't establish execution):")
    for name, hits in sorted(filemarks, key=lambda pair: (not any(t in pair[1] for t in ("SM-U600","Galaxy Buds On","GalaxyBudsOn","BudsOnDevice")), pair[0]))[:100]:
        out.append(name + ": " + ", ".join(hits))
    out.append("Completed static scan. Missing literals can reflect binary identifiers, resource encoding or an external component.")


def main():
    report_path = Path(sys.argv[1]); out = []
    try:
        url = "https://displaycatalog.mp.microsoft.com/v7.0/products/" + PRODUCT + "?market=US&languages=en-US"
        product = fetch_json(url)["Product"]
        sku = next(x["Sku"] for x in product["DisplaySkuAvailabilities"] if x["Sku"]["Properties"].get("Packages"))
        candidates = [p for p in sku["Properties"]["Packages"] if p["PackageFamilyName"] == FAMILY and "x64" in p["Architectures"]]
        p = max(candidates, key=lambda item: int(item["Version"]))
        out.append("Microsoft Store product " + PRODUCT + " catalog package " + p["PackageFullName"])
        out.append("Declared app services: " + ", ".join(e.split("-",1)[-1] for app in p["Applications"] for e in app["Extensions"] if e.startswith("AppService-")))
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            try:
                package = public_download(p, tmp)
            except (OSError, ValueError, KeyError, StopIteration) as error:
                status = getattr(error,"code",None)
                out.append("Direct Store delivery unavailable (" + type(error).__name__ + (f", HTTP {status}" if status else "") + ").")
                import shutil
                winget = shutil.which("winget")
                if not winget:
                    out.append("WinGet unavailable on this runner. Catalog-only result.")
                    return
                fetched = tmp / "winget"
                result = subprocess.run([winget, "download", "--exact", "--id", PRODUCT, "--source", "msstore",
                    "--architecture", "x64", "--skip-dependencies", "--skip-license", "--authentication-mode", "silent",
                    "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity",
                    "--download-directory", str(fetched)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=230)
                candidates = [f for f in fetched.rglob("*") if f.suffix.lower() in (".msix", ".appx", ".msixbundle", ".appxbundle") and 0 < f.stat().st_size <= LIMIT]
                if result.returncode or len(candidates) != 1:
                    out.append(f"WinGet exit code {result.returncode}. No single inspectable application. Catalog-only result.")
                    return
                package = candidates[0]
            with ZipFile(package) as archive:
                read_x64(archive, out)
    except (BadZipFile, KeyError, OSError, ValueError, StopIteration, subprocess.TimeoutExpired, ET.ParseError) as error:
        out.append("Static package analysis incomplete: " + type(error).__name__ + ".")
    finally:
        report_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        for line in out: report(line)


if __name__ == "__main__":
    main()
