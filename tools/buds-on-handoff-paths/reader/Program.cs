using System.Buffers.Binary;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Text.RegularExpressions;

internal static class Program
{
    public static int Main(string[] args)
    {
        if (args is ["--self-test"]) return SelfTest.Run();
        if (args.Length != 1 || !string.Equals(Path.GetFileName(args[0]), "EasyConnectLib.dll", StringComparison.OrdinalIgnoreCase))
            return 2;

        byte[] image;
        try
        {
            // Match the byte access used by the earlier reader. One open handle supplies
            // the complete snapshot, even if Windows renames the package while reading.
            using var input = new FileStream(args[0], FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete);
            long length = input.Length;
            if (length < 1 || length > 64 * 1024 * 1024) return 13;
            image = new byte[(int)length];
            input.ReadExactly(image);
            if (input.Length != length) return 12;
        }
        catch (Exception e) when (e is UnauthorizedAccessException or System.Security.SecurityException) { return 10; }
        catch (IOException e) when (OperatingSystem.IsWindows() && (e.HResult & 0xffff) is 32 or 33) { return 11; }
        catch (IOException) { return 12; }

        using var snapshot = new MemoryStream(image, writable: false);
        return Inspect(snapshot, Console.Out);
    }

    internal static bool InvalidMetadata(Exception e) =>
        e is BadImageFormatException or InvalidDataException or ArgumentException or InvalidOperationException
            or OverflowException or IndexOutOfRangeException or NotSupportedException;

    internal static int Inspect(Stream snapshot, TextWriter output)
    {
        using var pe = new PEReader(snapshot, PEStreamOptions.LeaveOpen);
        MetadataReader metadata;
        try
        {
            // Read raw metadata, without applying WinRT type projections.
            if (!pe.HasMetadata) return 20;
            metadata = pe.GetMetadataReader(MetadataReaderOptions.None);
        }
        catch (Exception e) when (InvalidMetadata(e)) { return 20; }

        using var body = new StringWriter();
        string? inventoryReason;
        if (metadata.MethodDefinitions.Count > CallsiteReader.MaxMethods)
            inventoryReason = "The method table exceeds the call-graph limit.";
        else
        {
            try
            {
                var scanner = new CallsiteReader(pe, metadata);
                inventoryReason = scanner.InventoryReason();
                if (inventoryReason == null) scanner.Write(body);
            }
            catch (Exception e) when (InvalidMetadata(e))
            {
                inventoryReason = "Managed metadata was located but the call graph could not be decoded.";
            }
        }

        if (inventoryReason == null) output.Write(body);
        else
        {
            output.WriteLine("Managed method inventory only.");
            output.WriteLine(inventoryReason);
        }
        CallsiteReader.WriteInventory(metadata, output);
        output.WriteLine(inventoryReason == null ? "Scan complete." : "Inventory complete.");
        return inventoryReason == null ? 0 : 21;
    }
}

internal sealed partial class CallsiteReader
{
    public const int MaxMethods = 65000;
    private const int MaxDepth = 5, MaxRootWalk = 2500, MaxPaths = 200;
    private readonly PEReader pe;
    private readonly MetadataReader metadata;
    private readonly Dictionary<MethodDefinitionHandle, Node> nodes = new();
    private int missingBodies, brokenBodies, unresolvedLocal, rootsWithTruncatedSearch;
    private int skippedRoots, omittedPaths;
    private static readonly Dictionary<ushort, OpCode> Opcodes = typeof(OpCodes).GetFields()
        .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!)
        .ToDictionary(op => unchecked((ushort)op.Value));
    private static readonly StringComparison IgnoreCase = StringComparison.OrdinalIgnoreCase;

    private sealed class Node
    {
        public string? Root;
        public bool HasDecodedBody;
        public List<(MethodDefinitionHandle To, string Via)> Edges { get; } = new();
        public SortedSet<string> Evidence { get; } = new(StringComparer.Ordinal);
    }
    private readonly record struct Member(string Type, string Name, MethodDefinitionHandle Local);

    public CallsiteReader(PEReader pe, MetadataReader metadata)
    {
        this.pe = pe;
        this.metadata = metadata;
        foreach (var handle in metadata.MethodDefinitions) nodes.Add(handle, new Node());
        foreach (var (handle, node) in nodes)
        {
            try { ReadMethod(handle, node); }
            catch (Exception e) when (Program.InvalidMetadata(e))
            {
                // Discard partial edges from this method. A malformed row cannot
                // erase already decoded edges in other methods.
                node.Edges.Clear();
                node.Evidence.Clear();
                brokenBodies++;
            }
        }
    }

    public string? InventoryReason()
    {
        if (!nodes.Values.Any(n => n.HasDecodedBody))
            return $"No usable managed method bodies. Native/abstract/absent = {missingBodies}; unreadable/oversized = {brokenBodies}.";
        if (nodes.Values.Any(n => n.Root != null) && !nodes.Values.Any(n => n.HasDecodedBody && n.Root != null))
            return "The switch candidates identified by name have no decodable method bodies.";
        return null;
    }

    private string Str(StringHandle h) => metadata.GetString(h);
    private static string Token(MethodDefinitionHandle h) => $"#{MetadataTokens.GetToken(h):X8}";
    private static string Tail(string s) => s[(s.LastIndexOf('.') + 1)..];
    private static bool Has(string s, string pattern) => s.Contains(pattern, IgnoreCase);
    private static bool SwitchName(string name) => new[] { "AutoSwitch", "SwitchAudio", "AudioSwitch", "SwitchBuds", "BudsSwitch" }
        .Any(term => Has(name, term));

    [GeneratedRegex(@"^[A-Za-z_][A-Za-z0-9_]{0,63}$", RegexOptions.CultureInvariant)]
    private static partial Regex SafeIdentifier();
    [GeneratedRegex(@"[0-9a-fA-F]{12}|password|secret|credential|bearertoken|accesskey", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex SensitiveIdentifier();
    private static string PublicName(string name)
    {
        return SafeIdentifier().IsMatch(name) && !SensitiveIdentifier().IsMatch(name) ? name : "(unnamed)";
    }
    private string RootName(MethodDefinitionHandle handle)
    {
        var method = metadata.GetMethodDefinition(handle);
        var declaring = metadata.GetTypeDefinition(method.GetDeclaringType());
        return $"{PublicName(Str(declaring.Name))}.{PublicName(Str(method.Name))} {Token(handle)}";
    }

    // This pass reads declarations directly and also works when there is no usable IL.
    public static void WriteInventory(MetadataReader metadata, TextWriter output)
    {
        const int rowLimit = 100000, displayLimit = 120;
        int examined = 0, matches = 0, unreadable = 0;
        output.WriteLine("Declared names in metadata (no call or runtime behavior implied):");
        foreach (var h in metadata.MethodDefinitions)
        {
            if (examined == rowLimit) break;
            examined++;
            try
            {
                var method = metadata.GetMethodDefinition(h);
                var type = metadata.GetString(metadata.GetTypeDefinition(method.GetDeclaringType()).Name);
                var name = metadata.GetString(method.Name);
                string? label = null;
                if (SwitchName(name) || (SwitchName(type) && !type.StartsWith('<') && !name.StartsWith('.')))
                    label = $"switch-related declaration / {PublicName(type)}.{PublicName(name)}";
                if (method.Attributes.HasFlag(MethodAttributes.PinvokeImpl))
                {
                    var import = method.GetImport();
                    var module = metadata.GetString(metadata.GetModuleReference(import.Module).Name);
                    if (module.Equals("DllBudsMsgFmt", IgnoreCase) || module.Equals("DllBudsMsgFmt.dll", IgnoreCase))
                        label = "formatter import declaration / " + PublicName(metadata.GetString(import.Name));
                }
                if (label != null && ++matches <= displayLimit) output.WriteLine($"{label} {Token(h)}");
            }
            catch (Exception e) when (Program.InvalidMetadata(e)) { unreadable++; }
        }
        output.WriteLine($"Inventory rows checked = {examined} of {metadata.MethodDefinitions.Count}; matching declarations = {matches}; omitted matches = {Math.Max(0, matches - displayLimit)}; unreadable rows = {unreadable}.");
    }

    // Return the declaring generic type, if the parent is a constructed generic type.
    private EntityHandle TypeOwner(EntityHandle type)
    {
        if (type.Kind != HandleKind.TypeSpecification) return type;
        var bytes = metadata.GetBlobReader(metadata.GetTypeSpecification((TypeSpecificationHandle)type).Signature);
        if (bytes.ReadSignatureTypeCode() != SignatureTypeCode.GenericTypeInstance ||
            bytes.ReadSignatureTypeCode() != SignatureTypeCode.TypeHandle) return default;
        return bytes.ReadTypeHandle();
    }

    private string TypeName(EntityHandle type)
    {
        type = TypeOwner(type);
        if (type.IsNil) return "";
        if (type.Kind == HandleKind.TypeDefinition)
        {
            var d = metadata.GetTypeDefinition((TypeDefinitionHandle)type);
            return Str(d.Namespace) + "." + Str(d.Name);
        }
        if (type.Kind == HandleKind.TypeReference)
        {
            var r = metadata.GetTypeReference((TypeReferenceHandle)type);
            return Str(r.Namespace) + "." + Str(r.Name);
        }
        return "";
    }

    private Member Describe(EntityHandle h, bool localLink = false)
    {
        if (h.IsNil) return default;
        if (h.Kind == HandleKind.MethodSpecification) h = metadata.GetMethodSpecification((MethodSpecificationHandle)h).Method;
        if (h.Kind == HandleKind.MethodDefinition)
        {
            var d = metadata.GetMethodDefinition((MethodDefinitionHandle)h);
            return new(TypeName(d.GetDeclaringType()), Str(d.Name), (MethodDefinitionHandle)h);
        }
        if (h.Kind == HandleKind.FieldDefinition)
        {
            var d = metadata.GetFieldDefinition((FieldDefinitionHandle)h);
            return new(TypeName(d.GetDeclaringType()), Str(d.Name), default);
        }
        if (h.Kind != HandleKind.MemberReference) return default;
        var member = metadata.GetMemberReference((MemberReferenceHandle)h);
        var owner = TypeOwner(member.Parent);
        MethodDefinitionHandle local = default;
        if (localLink && !owner.IsNil && owner.Kind == HandleKind.TypeDefinition)
        {
            var targetSig = metadata.GetBlobBytes(member.Signature);
            foreach (var cand in metadata.GetTypeDefinition((TypeDefinitionHandle)owner).GetMethods())
            {
                var def = metadata.GetMethodDefinition(cand);
                if (!metadata.StringComparer.Equals(def.Name, Str(member.Name)) ||
                    !metadata.GetBlobBytes(def.Signature).AsSpan().SequenceEqual(targetSig)) continue;
                local = cand;
                break;
            }
            if (local.IsNil) unresolvedLocal++;
        }
        return new(TypeName(owner), Str(member.Name), local);
    }

    private static string? PlatformEndpoint(Member member)
    {
        var type = member.Type;
        var name = member.Name;
        if (string.IsNullOrEmpty(type) || string.IsNullOrEmpty(name)) return null;
        string? category = type switch
        {
            "Windows.Devices.Bluetooth.Advertisement.BluetoothLEAdvertisementWatcher" => "BLE watcher",
            "Windows.Devices.Bluetooth.Advertisement.BluetoothLEAdvertisementPublisher" => "BLE advertiser",
            "Windows.Devices.Bluetooth.Advertisement.BluetoothLEManufacturerData" => "BLE manufacturer data",
            "Windows.Devices.Bluetooth.Rfcomm.RfcommDeviceService" => "RFCOMM service API",
            "Windows.Networking.Sockets.StreamSocket" when name == "ConnectAsync" => "stream socket (transport unspecified)",
            "Windows.Devices.Bluetooth.BluetoothDevice" when Has(name, "Rfcomm") => "RFCOMM service API",
            "Windows.Devices.Bluetooth.GenericAttributeProfile.GattCharacteristic" => "GATT characteristic API",
            "Windows.Devices.Bluetooth.BluetoothLEDevice" => "BLE device API",
            "Windows.Devices.Bluetooth.BluetoothDevice" when Has(name, "Connection") => "classic device API",
            _ => null
        };
        if (category != null) return $"{category} / {Tail(type)}.{(name == ".ctor" ? "constructor" : PublicName(name))}";
        // Application-level semantic names are evidence of a named call only.
        if (new[] { "GetMdeVersion", "SetMdeVersion", "SendMdeVersion", "GetHostVersion",
                    "SetHostVersion", "MDE_VERSION" }.Any(t => name.Equals(t, IgnoreCase)))
            return $"host-version name / {PublicName(Tail(type))}.{PublicName(name)}";
        if (Has(type, "BudsMsgFmt"))
            return $"Buds formatter member name / {PublicName(Tail(type))}.{PublicName(name)}";
        if ((Has(type,"Continuity") || Has(type,"Mcf")) && (Has(name,"Send") || Has(name,"Request") || Has(name,"Publish")))
            return $"continuity messaging name / {PublicName(Tail(type))}.{PublicName(name)}";
        if ((Has(type,"Buds") || Has(type,"Bluetooth")) && (Has(name,"Disconnect") || Has(name,"Reconnect")))
            return $"connection-control name / {PublicName(Tail(type))}.{PublicName(name)}";
        return null;
    }

    private void LinkAsync(MethodDefinitionHandle h, Node node)
    {
        var method = metadata.GetMethodDefinition(h);
        foreach (var attrHandle in method.GetCustomAttributes())
        {
            var attr = metadata.GetCustomAttribute(attrHandle);
            if (Describe(attr.Constructor).Type != "System.Runtime.CompilerServices.AsyncStateMachineAttribute") continue;
            var args = metadata.GetBlobReader(attr.Value);
            if (args.ReadUInt16() != 1) continue;
            var encoded = args.ReadSerializedString();
            if (encoded == null) continue;
            // The attribute specifies the exact generated type, distinguishing overloaded async methods.
            var declared = encoded.Split(',')[0];
            foreach (var child in metadata.GetTypeDefinition(method.GetDeclaringType()).GetNestedTypes())
            {
                var state = metadata.GetTypeDefinition(child);
                if (!declared.EndsWith("+" + Str(state.Name), StringComparison.Ordinal)) continue;
                foreach (var candidate in state.GetMethods())
                    if (metadata.StringComparer.Equals(metadata.GetMethodDefinition(candidate).Name, "MoveNext"))
                        node.Edges.Add((candidate, "async body"));
            }
        }
    }

    private void ReadMethod(MethodDefinitionHandle h, Node node)
    {
        var method = metadata.GetMethodDefinition(h);
        var name = Str(method.Name);
        var type = Str(metadata.GetTypeDefinition(method.GetDeclaringType()).Name);
        bool ordinary = !type.StartsWith('<') && !name.StartsWith(".", StringComparison.Ordinal) && !name.StartsWith('<') &&
                        !method.Attributes.HasFlag(MethodAttributes.SpecialName);
        if (!type.StartsWith('<') && method.Attributes.HasFlag(MethodAttributes.SpecialName) && SwitchName(name))
            node.Root = "explicitly switch-named accessor";
        else if (ordinary && SwitchName(name)) node.Root = "switch-named method";
        else if (ordinary && SwitchName(type)) node.Root = "member of switch-named type";

        if (method.RelativeVirtualAddress == 0) { missingBodies++; return; }
        if ((method.ImplAttributes & MethodImplAttributes.CodeTypeMask) != MethodImplAttributes.IL)
        { missingBodies++; return; }
        LinkAsync(h, node);
        var il = pe.GetMethodBody(method.RelativeVirtualAddress).GetILBytes();
        if (il == null || il.Length == 0 || il.Length > 256 * 1024) { brokenBodies++; return; }
        int pos = 0;
        while (pos < il.Length)
        {
            ushort code = il[pos++];
            if (code == 0xfe) { Ensure(il, pos, 1); code = (ushort)(0xfe00 | il[pos++]); }
            if (!Opcodes.TryGetValue(code, out var op)) throw new BadImageFormatException();
            int size = OperandSize(il, pos, op.OperandType);
            Ensure(il, pos, size);
            if (op == OpCodes.Ldstr)
            {
                var token = BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(pos));
                if ((token >> 24) != 0x70) throw new BadImageFormatException();
                string literal = metadata.GetUserString(MetadataTokens.UserStringHandle(token & 0xffffff));
                if (literal.Equals("SM-U600", IgnoreCase) || literal.Equals("Galaxy Buds On", IgnoreCase))
                    node.Evidence.Add("ldstr / exact " + (literal.Equals("SM-U600", IgnoreCase) ? "SM-U600" : "Galaxy Buds On") + " literal");
                if (literal.Equals("MDE_VERSION", IgnoreCase)) node.Evidence.Add("ldstr / exact MDE_VERSION literal");
                if (ordinary && node.Root == null && (literal.Equals("BudsAutoSwitch", IgnoreCase) || literal.Equals("AutoSwitchBuds", IgnoreCase)))
                    node.Root = "loads exact switch name";
            }
            if (op == OpCodes.Ldftn || op == OpCodes.Ldvirtftn)
            {
                var token = BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(pos));
                var target = Describe(MetadataTokens.EntityHandle(token), localLink: true);
                if (!target.Local.IsNil) node.Edges.Add((target.Local, "delegate target reference"));
            }
            if (op == OpCodes.Call || op == OpCodes.Callvirt || op == OpCodes.Newobj || op == OpCodes.Jmp)
            {
                var token = BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(pos));
                var member = Describe(MetadataTokens.EntityHandle(token), localLink: true);
                if (PlatformEndpoint(member) is { } end) node.Evidence.Add($"{op.Name} / {end}");
                if (!member.Local.IsNil)
                {
                    node.Edges.Add((member.Local, op.Name!));
                    var target = metadata.GetMethodDefinition(member.Local);
                    if (target.Attributes.HasFlag(MethodAttributes.PinvokeImpl))
                    {
                        var import = target.GetImport();
                        var module = Str(metadata.GetModuleReference(import.Module).Name);
                        if (module.Equals("DllBudsMsgFmt", IgnoreCase) || module.Equals("DllBudsMsgFmt.dll", IgnoreCase))
                            node.Evidence.Add($"{op.Name} / Buds formatter native import / {PublicName(Str(import.Name))}");
                    }
                }
            }
            if (op.OperandType == OperandType.InlineField)
            {
                var member = Describe(MetadataTokens.EntityHandle(BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(pos))));
                if (string.Equals(member.Name, "MDE_VERSION", IgnoreCase)) node.Evidence.Add($"{op.Name} / MDE_VERSION field");
                if (ordinary && node.Root == null && (string.Equals(member.Name, "BudsAutoSwitch", IgnoreCase) ||
                    string.Equals(member.Name, "AutoSwitchBuds", IgnoreCase))) node.Root = "references a switch-named field";
            }
            pos += size;
        }
        node.HasDecodedBody = true;
    }

    private static void Ensure(byte[] il, int pos, int length)
    {
        if (length < 0 || pos > il.Length - length) throw new BadImageFormatException();
    }
    private static int OperandSize(byte[] il, int pos, OperandType kind)
    {
        if (kind == OperandType.InlineSwitch)
        {
            Ensure(il, pos, 4);
            int n = BinaryPrimitives.ReadInt32LittleEndian(il.AsSpan(pos));
            if (n < 0 || n > (il.Length - pos - 4) / 4) throw new BadImageFormatException();
            return 4 + 4 * n;
        }
        return kind switch
        {
            OperandType.InlineNone => 0,
            OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
            OperandType.InlineVar => 2,
            OperandType.InlineI or OperandType.InlineBrTarget or OperandType.InlineField or
              OperandType.InlineMethod or OperandType.InlineSig or OperandType.InlineString or
              OperandType.InlineTok or OperandType.InlineType or OperandType.ShortInlineR => 4,
            OperandType.InlineI8 or OperandType.InlineR => 8,
            _ => throw new BadImageFormatException()
        };
    }

    public void Write(TextWriter output)
    {
        output.WriteLine("Static managed call sites in EasyConnectLib. Method tokens identify code locations in this file.");
        output.WriteLine("A path follows named call sites, an attributed async body or a delegate target reference. Referencing a target does not establish execution. Model selection, runtime traffic and payloads are unknown.");
        var roots = nodes.Where(pair => pair.Value.Root != null).OrderBy(pair => pair.Value.Root == "switch-named method" ? 0 : 1).ToArray();
        int emitted = 0, totalWalk = 0;
        skippedRoots = 0; omittedPaths = 0; rootsWithTruncatedSearch = 0;
        foreach (var (root, rootNode) in roots)
        {
            if (totalWalk >= 120000) { skippedRoots++; continue; }
            var work = new Queue<(MethodDefinitionHandle Here, string Path, int Depth)>();
            var seen = new HashSet<MethodDefinitionHandle> { root };
            var emittedForRoot = new HashSet<string>(StringComparer.Ordinal);
            work.Enqueue((root, "", 0));
            bool truncated = false;
            int visited = 0;
            while (work.TryDequeue(out var item))
            {
                if (++visited > MaxRootWalk || totalWalk++ >= 120000) { truncated = true; break; }
                var n = nodes[item.Here];
                foreach (string endpoint in n.Evidence)
                {
                    if (!emittedForRoot.Add(endpoint)) continue;
                    if (emitted >= MaxPaths) { omittedPaths++; continue; }
                    output.WriteLine($"{rootNode.Root} / {RootName(root)}{item.Path} -> {endpoint}");
                    emitted++;
                }
                foreach (var (to, via) in n.Edges)
                {
                    if (seen.Contains(to)) continue;
                    if (item.Depth >= MaxDepth) { truncated = true; continue; }
                    seen.Add(to);
                    work.Enqueue((to, item.Path + $" -> {via} {Token(to)}", item.Depth + 1));
                }
            }
            if (truncated) rootsWithTruncatedSearch++;
        }
        output.WriteLine($"Methods = {nodes.Count}; switch candidates = {roots.Length}; displayed paths = {emitted}; omitted matches = {omittedPaths}.");
        output.WriteLine($"Depth limit = {MaxDepth}; limited searches = {rootsWithTruncatedSearch}; unvisited roots = {skippedRoots}; native/abstract/absent IL bodies = {missingBodies}; unreadable or oversized bodies = {brokenBodies}; unresolved local method references = {unresolvedLocal}.");
        output.WriteLine("Each candidate shows one shortest path per endpoint. Native internals, external helper bodies, dynamic dispatch, runtime callback registration, indirect calls, and numeric constants are outside this check.");
    }
}
