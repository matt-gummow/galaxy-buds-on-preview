"""Build-input fix for the empty-repeater accessibility crash in FluentAvalonia 3.1.0."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("fluent_source", type=Path)
parser.add_argument("local_feed", type=Path)
parser.add_argument("restore_config", type=Path)
args = parser.parse_args()
source = args.fluent_source / "src/FluentAvalonia/UI/Controls/Repeater/Automation/FAItemsRepeaterAutomationPeer.cs"
old = "var childrenPeers = base.GetChildrenCore();"
new = "var childrenPeers = base.GetChildrenCore() ?? Array.Empty<AutomationPeer>();"
text = source.read_text(encoding="utf-8")
if text.count(old) == 1 and new not in text:
    source.write_text(text.replace(old, new), encoding="utf-8")
elif text.count(new) != 1 or old in text:
    raise SystemExit("Unexpected FluentAvalonia accessibility source")

args.local_feed.mkdir(parents=True, exist_ok=True)
config = ET.Element("configuration")
sources = ET.SubElement(config, "packageSources")
ET.SubElement(sources, "clear")
ET.SubElement(sources, "add", key="HandoffLocal", value=str(args.local_feed.resolve()))
ET.SubElement(sources, "add", key="nuget", value="https://api.nuget.org/v3/index.json")
mapping = ET.SubElement(config, "packageSourceMapping")
local = ET.SubElement(mapping, "packageSource", key="HandoffLocal")
ET.SubElement(local, "package", pattern="FluentAvaloniaUI")
public = ET.SubElement(mapping, "packageSource", key="nuget")
ET.SubElement(public, "package", pattern="*")
ET.indent(config)
args.restore_config.parent.mkdir(parents=True, exist_ok=True)
ET.ElementTree(config).write(args.restore_config, encoding="utf-8", xml_declaration=True)
print("Patched the empty accessibility child list and wrote the mapped restore configuration.")
