"""Inspect official Store distributions of the two Samsung host apps without installing them."""
import base64
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

PRODUCTS = (
    ("Galaxy Connect", "9NGW9K44GQ5F", "SAMSUNGELECTRONICSCoLtd.SamsungContinuityService_wyx1vj98g3asy", "4.6.1327.0"),
    ("Samsung Settings", "9P2TBWSHK6HJ", "SAMSUNGELECTRONICSCO.LTD.SamsungSettings1.5_3c1yjt4zspk6g", "8.5.7.0"),
)
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


def public_download(p, family, tmp):
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
    identity, publisher_id = family.lower().rsplit("_", 1)
    for f in files:
        moniker = f["FileMoniker"].lower()
        ext = Path(f["FileId"]).suffix.lower()
        if not moniker.startswith(identity + "_") or not moniker.endswith("_" + publisher_id):
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
    path = tmp / ("package" + Path(f["FileId"]).suffix)
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


def read_x64(archive, out, identity_name, installed):
    if "AppxManifest.xml" in archive.namelist():
        inspect_package(archive, out, identity_name, installed)
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
        inspect_package(nested, out, identity_name, installed)


def inspect_package(archive, out, identity_name, installed):
    root = ET.fromstring(archive.read("AppxManifest.xml"))
    identity = next(x for x in root if x.tag.split("}")[-1] == "Identity")
    if identity.get("Name", "").casefold() != identity_name.casefold() or identity.get("ProcessorArchitecture", "neutral").lower() not in ("x64", "neutral"):
        raise ValueError("Unexpected inner package identity or architecture")
    out.append(f'Inspected {identity.get("Name")} {identity.get("Version")} ({identity.get("ProcessorArchitecture")}).')
    out.append("Matches reported installed version: " + str(identity.get("Version") == installed))
    modules = []
    filemarks = []
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


def inspect_product(label, product_id, family, installed, out):
    out.append(f"{label}: Microsoft Store {product_id}; reported installed version {installed}.")
    try:
        url = "https://displaycatalog.mp.microsoft.com/v7.0/products/" + product_id + "?market=US&languages=en-US"
        product = fetch_json(url)["Product"]
        if product["ProductId"].upper() != product_id:
            out.append("Catalog product ID mismatch. Package analysis incomplete.")
            return
        candidates = [
            p for sku in product["DisplaySkuAvailabilities"] for p in sku["Sku"]["Properties"].get("Packages", [])
            if p["PackageFamilyName"].casefold() == family.casefold() and "x64" in p["Architectures"]
        ]
        if not candidates:
            out.append("Expected x64 package family unavailable. Package analysis incomplete.")
            return
        p = max(candidates, key=lambda item: (item["PackageFullName"].split("_")[1] == installed, int(item["Version"])))
        out.append("Microsoft Store catalog package " + p["PackageFullName"])
        out.append("Declared app services: " + ", ".join(e.split("-",1)[-1] for app in p["Applications"] for e in app["Extensions"] if e.startswith("AppService-")))
        with tempfile.TemporaryDirectory() as temp:
            tmp = Path(temp)
            try:
                package = public_download(p, family, tmp)
            except (OSError, ValueError, KeyError, StopIteration) as error:
                status = getattr(error,"code",None)
                out.append("Direct Store delivery unavailable (" + type(error).__name__ + (f", HTTP {status}" if status else "") + ").")
                winget = shutil.which("winget")
                if not winget:
                    out.append("WinGet unavailable on this runner. Catalog-only result.")
                    return
                fetched = tmp / "winget"
                result = subprocess.run([winget, "download", "--exact", "--id", product_id, "--source", "msstore",
                    "--architecture", "x64", "--skip-dependencies", "--skip-license", "--authentication-mode", "silent",
                    "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity",
                    "--download-directory", str(fetched)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=230)
                candidates = [f for f in fetched.rglob("*") if f.suffix.lower() in (".msix", ".appx", ".msixbundle", ".appxbundle") and 0 < f.stat().st_size <= LIMIT]
                if result.returncode or len(candidates) != 1:
                    code = result.returncode & 0xffffffff
                    detail = " Interactive authentication required." if code == 0x8A150076 else ""
                    out.append(f"WinGet exit code 0x{code:08X}.{detail} No single inspectable application. Catalog-only result.")
                    return
                package = candidates[0]
            with ZipFile(package) as archive:
                read_x64(archive, out, family.rsplit("_", 1)[0], installed)
    except (BadZipFile, KeyError, OSError, ValueError, StopIteration, subprocess.TimeoutExpired, ET.ParseError) as error:
        out.append("Static package analysis incomplete: " + type(error).__name__ + ".")


def main():
    report_path = Path(sys.argv[1])
    out = []
    for spec in PRODUCTS:
        product_report = []
        inspect_product(*spec, product_report)
        out.extend(product_report)
        for line in product_report:
            report(line)
    report_path.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
