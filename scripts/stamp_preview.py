from pathlib import Path
import sys

root = Path(sys.argv[1])
props = root / "GalaxyBudsClient/Application.props"
original = props.read_text()
if original.count("5.2.1.0") != 2:
    raise SystemExit("Unexpected baseline app versions")
props.write_text(original.replace("5.2.1.0", "5.2.1.6"))
settings = root / "GalaxyBudsClient/Interface/Pages/SettingsPage.axaml"
original = settings.read_text()
marker = 'Text="Galaxy Buds Manager"'
if original.count(marker) != 1:
    raise SystemExit("Unexpected Settings heading")
settings.write_text(original.replace(marker, 'Text="Galaxy Buds Manager · Buds On preview 6"'))
print("Stamped Buds On preview 6 (5.2.1.6)")
