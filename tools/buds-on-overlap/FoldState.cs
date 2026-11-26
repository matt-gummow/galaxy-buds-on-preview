using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;

public sealed class FoldSnapshot
{
    public string A2dp = "unknown", Hfp = "unknown";
    public string A2dpActive = "unknown", HfpActive = "unknown";
    public string A2dpPlaying = "unknown", HfpAudio = "unknown";
    public string Evidence;
    public FoldSnapshot(string evidence) { Evidence = evidence; }
}

// Only the current Java profile dump is evidence. Bond records establish identity only.
// No address, name, arbitrary device text or controller payload is copied into a snapshot.
public static class FoldState
{
    private const string Address = @"(?:[0-9A-FX]{2}:){5}[0-9A-FX]{2}";
    private static readonly RegexOptions Options = RegexOptions.IgnoreCase | RegexOptions.CultureInvariant;
    private static readonly Regex Bond = new Regex(@"^(" + Address + @")(?:\s*=>\s*(" + Address +
        @"))?\s+\[\s*(?:DUAL|BR/EDR|CLASSIC|LE|\?+)\s*\](?:\[\s*0x[0-9A-F]+\s*\])?\s*(.*?)\s*$", Options);
    private static readonly Regex Machine = new Regex(@"^={2,}\s+(A2dpStateMachine|StateMachine) for (" +
        Address + @")( \(Active\))?\s+={2,}$", Options);
    private static readonly Regex Current = new Regex(@"^mConnectionState:\s*(?:STATE_)?(connected|disconnected|connecting|disconnecting|[0-3])(?:,\s*mLastConnectionState:\s*\w+)?$", Options);
    private static readonly Regex Active = new Regex(@"^mActiveDevice:\s*(" + Address + @"|null)$", Options);

    private sealed class BondRow
    {
        public readonly string Address1, Address2, Name;
        public BondRow(Match m) { Address1 = m.Groups[1].Value; Address2 = m.Groups[2].Value; Name = m.Groups[3].Value; }
    }

    private static bool Equal(string left, string right) { return String.Equals(left, right, StringComparison.OrdinalIgnoreCase); }
    private static bool Redacted(string address)
    {
        return Regex.IsMatch(address, @"^(?:(?:XX:){3}(?:[0-9A-F]{2}:){2}|(?:XX:){4}[0-9A-F]{2}:)[0-9A-F]{2}$", Options);
    }

    private static bool SameVisibleSuffix(string first, string second)
    {
        if (first.Length != 17 || second.Length != 17) return false;
        int start = Math.Max(first.LastIndexOf("X", StringComparison.OrdinalIgnoreCase), second.LastIndexOf("X", StringComparison.OrdinalIgnoreCase));
        return Equal(first.Substring(start + 1), second.Substring(start + 1));
    }

    private static bool Matches(string token, string target, string name, List<BondRow> bonds, bool completeRoster)
    {
        if (Equal(token, target)) return true;
        if (!completeRoster || !Redacted(token) || !SameVisibleSuffix(token, target)) return false;
        int candidates = 0;
        bool bound = false;
        foreach (BondRow row in bonds)
        {
            bool suffix = SameVisibleSuffix(row.Address1, token) || SameVisibleSuffix(row.Address2, token);
            if (!suffix) continue;
            candidates++;
            bound = Equal(row.Address1, target) || Equal(row.Address2, target)
                || (Redacted(row.Address1) && Equal(row.Address1, token) && name.Length != 0 && Equal(row.Name, name));
        }
        return candidates == 1 && bound;
    }

    private static string ProfileValue(string value)
    {
        if (value == "2" || Equal(value, "connected")) return "connected";
        if (value == "0" || Equal(value, "disconnected")) return "disconnected";
        return "unknown";
    }

    public static FoldSnapshot Parse(string dump, string address, string name)
    {
        var result = new FoldSnapshot("no-target-state");
        string target = (address ?? "").Replace(":", "").Replace("-", "").Trim();
        if (!Regex.IsMatch(target, "^[0-9a-fA-F]{12}$")) return result;
        target = Regex.Replace(target.ToUpperInvariant(), "(..)(?=.)", "$1:");
        if (target == "00:00:00:00:00:00" || target == "FF:FF:FF:FF:FF:FF") return result;
        name = (name ?? "").Trim();
        var bonds = new List<BondRow>();
        bool inBonds = false, sawBonds = false, complete = false, rosterInvalid = false;
        // Retain only the two exact profile sections and synthetic field names.
        var profileLines = new List<string>();
        int profile = 0;
        using (var input = new StringReader(dump ?? ""))
        {
            string raw;
            while ((raw = input.ReadLine()) != null)
            {
                string s = raw.Trim();
                if (s == "Bonded devices:")
                {
                    if (sawBonds) rosterInvalid = true;
                    sawBonds = true; inBonds = true; profile = 0; continue;
                }
                if (inBonds)
                {
                    Match bond = Bond.Match(s);
                    if (bond.Success) { bonds.Add(new BondRow(bond)); continue; }
                    if (s.Length == 0 || raw.Length == s.Length || s.StartsWith("Profile: "))
                    { complete = true; inBonds = false; }
                    else { rosterInvalid = true; continue; }
                }
                if (s.StartsWith("Profile: "))
                {
                    profile = s == "Profile: A2dpService" ? 1 : s == "Profile: HeadsetService" ? 2 : 0;
                    profileLines.Add(profile == 0 ? "!" : s);
                    continue;
                }
                if (profile == 0 || s.Length == 0) continue;
                if (!Char.IsWhiteSpace(raw[0])) { profile = 0; profileLines.Add("!"); continue; }
                if (s.StartsWith("=") || s.StartsWith("mActiveDevice:") || s.StartsWith("mCurrentDevice:")
                    || s.StartsWith("mConnectionState:") || s.StartsWith("mIsPlaying:")
                    || s.StartsWith("mAudioState:") || s.StartsWith("StateMachine:") || s.StartsWith("State machine logs"))
                    profileLines.Add(s);
            }
        }
        bool rosterReady = complete && !rosterInvalid;
        int[] sections = new int[3], targetBlocks = new int[3];
        bool[] routeSeen = new bool[3], repeated = new bool[3];
        bool targetBlock = false, beforeBlocks = false;
        profile = 0;
        foreach (string s in profileLines)
        {
            if (s == "!" || s.StartsWith("Profile: "))
            {
                profile = s == "!" ? 0 : s == "Profile: A2dpService" ? 1 : 2;
                sections[profile]++;
                targetBlock = false; beforeBlocks = true;
                continue;
            }
            if (profile == 0) continue;
            if (s.StartsWith("="))
            {
                Match block = Machine.Match(s);
                beforeBlocks = false;
                targetBlock = block.Success && (profile == 1 ? block.Groups[1].Value == "A2dpStateMachine" : block.Groups[1].Value == "StateMachine")
                    && Matches(block.Groups[2].Value, target, name, bonds, rosterReady);
                if (targetBlock)
                {
                    targetBlocks[profile]++;
                    if (profile == 1 && block.Groups[3].Success && !routeSeen[1]) result.A2dpActive = "active";
                }
                continue;
            }
            if (beforeBlocks && s.StartsWith("mActiveDevice:"))
            {
                Match field = Active.Match(s);
                string active = field.Success && Matches(field.Groups[1].Value, target, name, bonds, rosterReady) ? "active" : "unknown";
                if (routeSeen[profile]) active = "unknown";
                routeSeen[profile] = true;
                if (profile == 1) result.A2dpActive = active; else result.HfpActive = active;
                continue;
            }
            if (!targetBlock) continue;
            if (s.StartsWith("StateMachine:") || s.StartsWith("State machine logs")) { targetBlock = false; continue; }
            if (s.StartsWith("mCurrentDevice:") && !Matches(s.Substring(15).Trim(), target, name, bonds, rosterReady))
            { repeated[profile] = true; targetBlock = false; continue; }
            Match state = Current.Match(s);
            if (state.Success)
            {
                string value = ProfileValue(state.Groups[1].Value);
                if (profile == 1) { if (result.A2dp != "unknown") repeated[1] = true; result.A2dp = value; }
                else { if (result.Hfp != "unknown") repeated[2] = true; result.Hfp = value; }
            }
            if (profile == 1 && (s == "mIsPlaying: true" || s == "mIsPlaying: false"))
                result.A2dpPlaying = s.EndsWith("true") ? "yes" : "no";
            if (profile == 2 && (s == "mAudioState: 12" || s == "mAudioState: 10"))
                result.HfpAudio = s.EndsWith("12") ? "connected" : "disconnected";
        }
        if (sections[1] > 1 || targetBlocks[1] > 1 || repeated[1]) result.A2dp = result.A2dpPlaying = result.A2dpActive = "unknown";
        if (sections[2] > 1 || targetBlocks[2] > 1 || repeated[2]) result.Hfp = result.HfpAudio = result.HfpActive = "unknown";
        if (result.A2dp != "connected") result.A2dpPlaying = "unknown";
        if (result.Hfp != "connected") result.HfpAudio = "unknown";
        if (result.A2dp != "unknown" || result.Hfp != "unknown") result.Evidence = "target-profile";
        else if (result.A2dpActive == "active" || result.HfpActive == "active") result.Evidence = "selected-device-only";
        return result;
    }
}
