using System;
using System.IO;
using System.Runtime.InteropServices;

class HelperShim
{
    [DllImport("msvcrt.dll", CharSet = CharSet.Unicode, CallingConvention = CallingConvention.Cdecl)]
    private static extern int _wspawnvp(int mode, string cmdname, string[] argv);

    private const int _P_WAIT = 0;

    static int Main(string[] args)
    {
        string binDir = AppDomain.CurrentDomain.BaseDirectory;
        string addonDir = Path.GetFullPath(Path.Combine(binDir, ".."));
        string scriptPath = Path.Combine(addonDir, "swofty_helper.py");

        string[] candidates = new string[] {
            Path.Combine(addonDir, ".venv", "Scripts", "python.exe"),
            @"c:\Users\Jorge\.gemini\antigravity\scratch\f1_mods\ai_race_engineer\.venv\Scripts\python.exe",
            "python.exe"
        };

        string pythonExe = "python.exe";
        foreach (string c in candidates)
        {
            if (File.Exists(c))
            {
                pythonExe = c;
                break;
            }
        }

        if (!File.Exists(scriptPath))
        {
            scriptPath = @"c:\Users\Jorge\.gemini\antigravity\scratch\f1_mods\ai_race_engineer\swofty_helper.py";
        }

        Directory.SetCurrentDirectory(Path.GetDirectoryName(scriptPath));

        string[] argv = new string[args.Length + 4];
        argv[0] = "\"" + pythonExe + "\"";
        argv[1] = "-u";
        argv[2] = "\"" + scriptPath + "\"";
        for (int i = 0; i < args.Length; i++)
        {
            argv[i + 3] = "\"" + args[i] + "\"";
        }
        argv[args.Length + 3] = null;

        return _wspawnvp(_P_WAIT, pythonExe, argv);
    }
}
