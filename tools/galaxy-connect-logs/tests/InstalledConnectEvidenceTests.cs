using System;
using System.IO;

public static class InstalledConnectEvidenceTests
{
    private sealed class AutoSwitchBudsFixture
    {
        static AutoSwitchBudsFixture() { throw new Exception("Test module was executed"); }
        public void OnAudioFocusChanged() {}
        public void OnCallback() {}
        public void DisconnectViewModel() {}
        public void OnWindowFocusChanged() {}
    }
    public static void Run()
    {
        string folder=Path.Combine(Path.GetTempPath(),"buds-host-fixture-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        try
        {
            File.Copy(typeof(InstalledConnectEvidenceTests).Assembly.Location,Path.Combine(folder,"EasyConnect2.dll"));
            File.WriteAllText(Path.Combine(folder,"unknown-private.txt"),"SECRET_PRIVATE_TEST");
            using(var w=new StringWriter())
            {
                InstalledConnectEvidence.Write(null,folder,w);
                string s=w.ToString();
                if(!s.Contains("registered folder unavailable") || !s.Contains("recognized components inspected = 1.") ||
                    !s.Contains("name mentions audio focus") || s.Contains("name mentions a call event") || s.Contains("name mentions a Bluetooth or Buds link") || s.Contains("SECRET_PRIVATE") || s.Contains(folder) || s.Contains("OnAudioFocusChanged"))
                    throw new Exception("Installed host scanner fixture failed.");
            }
        }
        finally { Directory.Delete(folder,true); }
    }
}
