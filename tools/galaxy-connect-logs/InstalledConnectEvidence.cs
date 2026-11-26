using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

// Inspects selected installed files as bytes. No module is loaded into the CLR.
public static class InstalledConnectEvidence
{
    private static readonly string[] Files = {
        "EasyConnectLib.dll", "EasyConnect2.dll", "DllBudsMsgFmt.dll", "ContinuityFeatureApps.dll",
        "SamsungSettings.dll", "SamsungSettingsService.dll", "WinRT.Host.dll", "SamsungSettingsHost.exe"
    };
    private static readonly string[] Terms = {
        "SM-U600", "SM-R640", "Galaxy Buds On", "Galaxy Buds4 Pro", "BudsOnDevice",
        "BudsBLEAdvertisementBackgroundTask", "AutoSwitchBuds", "BudsAutoSwitch", "ModuleEasyConnect",
        "DllBudsMsgFmt", "BluetoothLEAdvertisementWatcher", "BluetoothLEAudio",
        "MDE_VERSION", "AUTO_SWITCH_AUDIO_OUTPUT", "PROFILE_CONTROL"
    };
    private static readonly string[][] MethodTerms = {
        new[] { "IncomingCall", "OutgoingCall", "CallState", "CallAudio", "OnCallStarted", "OnCallEnded", "OnCallChanged", "AnswerCall", "EndCall" },
        new[] { "MediaState", "MediaPlaying", "MediaSession", "MediaPlayback", "MediaStream" },
        new[] { "PlaybackState", "PlaybackStarted", "PlaybackStopped", "PlaybackChanged" },
        new[] { "AudioFocus" }, new[] { "AudioOwner", "PlaybackOwner", "StreamOwner" },
        new[] { "AdvertisementWatcher", "AdvertisementReceived", "BleAdvertisement", "AdvertisementPublisher" },
        new[] { "AudioTransport", "BluetoothTransport", "TransportType" },
        new[] { "AutoSwitch", "SwitchAudio", "AudioSwitch", "BudsSwitch" },
        new[] { "BluetoothConnected", "BluetoothDisconnected", "BudsConnected", "BudsDisconnected" },
        new[] { "MdeVersion", "HostVersion", "MDE_VERSION" }
    };
    private static readonly string[] RoleLabels = { "name mentions a call event or call audio", "name mentions media state or session",
        "name mentions a playback event", "name mentions audio focus", "name mentions an audio owner", "name mentions a BLE advertisement or watcher",
        "name mentions a transport term", "name mentions auto or audio switching", "name mentions a Bluetooth or Buds link",
        "name mentions a host or MDE version" };
    private const int MaxFile = 48 * 1024 * 1024;

    public static void Write(string connectFolder, string settingsFolder, TextWriter output)
    {
        output.WriteLine("Installed host software (static evidence only).");
        ScanPackage("Galaxy Connect", connectFolder, output);
        ScanPackage("Samsung Settings", settingsFolder, output);
        output.WriteLine("Presence means an identifier exists in this version. Exact operations, model selection, and behavior during the earlier test require separate evidence. Missing names may reflect native code or other components.");
    }

    private static bool Skippable(Exception e)
    {
        return e is IOException || e is UnauthorizedAccessException || e is System.Security.SecurityException;
    }

    private static void ScanPackage(string label, string folder, TextWriter output)
    {
        if (String.IsNullOrEmpty(folder) || !Directory.Exists(folder)) { output.WriteLine(label + ": registered folder unavailable."); return; }
        var paths = new Dictionary<string,List<string>>(StringComparer.OrdinalIgnoreCase);
        foreach (string name in Files) paths[name] = new List<string>();
        bool partial = false;
        var dirs = new Queue<string>();
        dirs.Enqueue(folder);
        int walked = 0, entries = 0;
        while (dirs.Count > 0 && walked++ < 800 && entries < 18000)
        {
            string dir = dirs.Dequeue();
            try
            {
                if ((File.GetAttributes(dir) & FileAttributes.ReparsePoint) != 0) { partial = true; continue; }
                foreach (string path in Directory.EnumerateFileSystemEntries(dir))
                {
                    if (++entries > 18000) { partial = true; break; }
                    FileAttributes attr = File.GetAttributes(path);
                    if ((attr & FileAttributes.ReparsePoint) != 0) { partial = true; continue; }
                    if ((attr & FileAttributes.Directory) != 0) { dirs.Enqueue(path); continue; }
                    List<string> matches;
                    if (paths.TryGetValue(Path.GetFileName(path), out matches))
                    {
                        if (matches.Count < 3) matches.Add(path); else partial = true;
                    }
                }
            }
            catch (Exception e) { if (!Skippable(e)) throw; partial = true; }
        }
        partial |= dirs.Count > 0;
        long budget = 240L * 1024 * 1024;
        int examined = 0;
        foreach (string name in Files)
        {
            foreach (string path in paths[name])
            {
                try
                {
                    long size = new FileInfo(path).Length;
                    if (size < 2 || size > budget || size > MaxFile) { partial = true; continue; }
                    byte[] bytes;
                    using (var s = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete))
                    {
                        if (s.Length != size) { partial = true; continue; }
                        using (var reader = new BinaryReader(s)) bytes = reader.ReadBytes((int)size);
                    }
                    budget -= size;
                    if (bytes.LongLength != size || bytes[0] != (byte)'M' || bytes[1] != (byte)'Z') { partial = true; continue; }
                    examined++;
                    var markers = new List<string>();
                    string view = Encoding.ASCII.GetString(bytes);
                    foreach (string term in Terms)
                    {
                        string wide = Encoding.ASCII.GetString(Encoding.Unicode.GetBytes(term));
                        if (view.IndexOf(term,StringComparison.OrdinalIgnoreCase) >= 0 || view.IndexOf(wide,StringComparison.OrdinalIgnoreCase) >= 0)
                            markers.Add(term);
                    }
                    output.WriteLine(label + " / " + name + " | exact-name literal search: " + (markers.Count == 0 ? "none" : String.Join(", ",markers)));
                    var roles = new SortedSet<string>(StringComparer.Ordinal);
                    bool managed = ManagedRoles(bytes, roles);
                    output.WriteLine(label + " / " + name + " | switching-related managed type and method names: " +
                        (!managed ? "metadata unavailable or unsupported" : roles.Count == 0 ? "no matching names" : String.Join(", ",roles)));
                }
                catch (Exception e) { if (!Skippable(e)) throw; partial = true; }
            }
        }
        output.WriteLine(label + ": recognized components inspected = " + examined + (partial ? " (partial coverage)." : "."));
    }

    // ECMA-335 compressed tables. Resolve TypeDef.MethodList only; no IL, code,
    // external references or custom attributes are executed or resolved.
    private sealed class Bytes
    {
        internal readonly byte[] Data;
        internal Bytes(byte[] b) { Data = b; }
        internal void Range(int at,int n) { if (at < 0 || n < 0 || (long)at+n > Data.Length) throw new InvalidDataException(); }
        internal int U16(int at) { Range(at,2); return Data[at] | (Data[at+1]<<8); }
        internal uint U32(int at) { Range(at,4); return (uint)(Data[at] | Data[at+1]<<8 | Data[at+2]<<16 | Data[at+3]<<24); }
        internal int Num(int at,int width) { return width==2 ? U16(at) : checked((int)U32(at)); }
        internal string Name(int at,int end,int max) {
            if (end < 0 || end > Data.Length || at < 0 || at >= end) return "";
            int i=at; while(i<end && i-at<max && Data[i]!=0) i++;
            if (i>=end || Data[i]!=0) return "";
            return Encoding.UTF8.GetString(Data,at,i-at);
        }
        internal int Map(uint rva,int sections,int count) {
            for (int i=0;i<count;i++) {
                int s=checked(sections+40*i); uint address=U32(s+12), raw=U32(s+16);
                if (rva>=address && rva-address<raw) {
                    int result=checked((int)((long)U32(s+20)+rva-address)); Range(result,1); return result;
                }
            }
            throw new InvalidDataException();
        }
    }
    private static bool ManagedRoles(byte[] bytes, SortedSet<string> roles)
    {
        try
        {
            var b=new Bytes(bytes);
            checked {
                int pe=b.Num(60,4);
                if (b.U32(pe)!=0x4550) return false;
                int count=b.U16(pe+6), optional=pe+24, magic=b.U16(optional), optionalSize=b.U16(pe+20);
                if (count>128 || (magic!=0x10b && magic!=0x20b)) return false;
                int dir=optional+(magic==0x20b?112:96), sections=optional+optionalSize;
                if (dir+8*15>sections) return false;
                uint cliRva=b.U32(dir+8*14);
                if (cliRva==0) return false;
                int cli=b.Map(cliRva,sections,count), root=b.Map(b.U32(cli+8),sections,count);
                if (b.U32(root)!=0x424a5342) return false;
                int metadataEnd=root+b.Num(cli+12,4);
                b.Range(root,metadataEnd-root);
                int pos=(root+16+b.Num(root+12,4)+3)&~3, streams=b.U16(pos+2);
                if (streams>32) return false;
                pos+=4; int tables=0, tend=0, strings=0, send=0;
                for(int i=0;i<streams;i++) {
                    int start=root+b.Num(pos,4), end=start+b.Num(pos+4,4);
                    string name=b.Name(pos+8,metadataEnd,32);
                    if (name.Length==0 || end>metadataEnd) return false;
                    if(name=="#~"){tables=start;tend=end;} else if(name=="#Strings"){strings=start;send=end;}
                    pos=(pos+8+name.Length+1+3)&~3;
                }
                if(tables==0 || strings==0 || tables+24>tend) return false;
                int heap=bytes[tables+6], str=(heap&1)!=0?4:2, guid=(heap&2)!=0?4:2, blob=(heap&4)!=0?4:2;
                int[] rows=new int[64]; pos=tables+24;
                for(int i=0;i<64;i++) if ((bytes[tables+8+i/8]&(1<<(i%8)))!=0) {rows[i]=b.Num(pos,4);pos+=4;}
                if(rows[3]!=0 || rows[5]!=0 || rows[2]>150000 || rows[6]>1000000 || pos>tend) return false;
                int resolution=Math.Max(Math.Max(rows[0],rows[26]),Math.Max(rows[35],rows[1]))>=16384?4:2;
                int typeRef=Math.Max(rows[2],Math.Max(rows[1],rows[27]))>=16384?4:2;
                int fieldIndex=rows[4]>=65536?4:2, methodIndex=rows[6]>=65536?4:2, paramIndex=rows[8]>=65536?4:2;
                int types=pos+rows[0]*(2+str+3*guid)+rows[1]*(resolution+2*str);
                int typeSize=4+2*str+typeRef+fieldIndex+methodIndex, methodSize=8+str+blob+paramIndex;
                int methods=types+rows[2]*typeSize+rows[4]*(2+str+blob);
                if(methods+rows[6]*methodSize>tend)return false;
                for(int i=0;i<rows[2];i++) {
                    int t=types+i*typeSize;
                    string type=b.Name(strings+b.Num(t+4,str),send,512);
                    if(!(type.IndexOf("Buds",StringComparison.OrdinalIgnoreCase)>=0 || type.IndexOf("EasyConnect",StringComparison.OrdinalIgnoreCase)>=0 || type.IndexOf("AutoSwitch",StringComparison.OrdinalIgnoreCase)>=0))continue;
                    int first=b.Num(t+typeSize-methodIndex,methodIndex);
                    int stop=i+1<rows[2]?b.Num(t+2*typeSize-methodIndex,methodIndex):rows[6]+1;
                    if(first<1 || stop<first || stop>rows[6]+1)return false;
                    for(int m=first;m<stop;m++){
                        string method=b.Name(strings+b.Num(methods+(m-1)*methodSize+8,str),send,512);
                        for(int j=0;j<MethodTerms.Length;j++)
                            foreach(string term in MethodTerms[j])
                                if(method.IndexOf(term,StringComparison.OrdinalIgnoreCase)>=0) { roles.Add(RoleLabels[j]); break; }
                    }
                }
            }
            return true;
        }
        catch(InvalidDataException){return false;}
        catch(OverflowException){return false;}
    }
}
