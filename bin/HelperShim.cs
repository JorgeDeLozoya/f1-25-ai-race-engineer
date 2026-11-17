using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

[assembly: AssemblyTitle("AI Race Engineer Swofty Helper")]
[assembly: AssemblyDescription("Launches swofty_helper.py for F1 25/26 AI Race Engineer")]
[assembly: AssemblyProduct("F1 25/26 AI Race Engineer")]
[assembly: AssemblyCompany("JorgeDelo")]
[assembly: AssemblyVersion("1.0.3.0")]
[assembly: AssemblyFileVersion("1.0.3.0")]

class HelperShim
{
    static string QuoteArg(string arg)
    {
        if (string.IsNullOrEmpty(arg))
            return "\"\"";
        if (arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
            return arg;
        return "\"" + arg.Replace("\"", "\\\"") + "\"";
    }

    static int Main(string[] args)
    {
        string binDir = AppDomain.CurrentDomain.BaseDirectory;
        string addonDir = Path.GetFullPath(Path.Combine(binDir, ".."));
        string scriptPath = Path.Combine(addonDir, "swofty_helper.py");

        if (!File.Exists(scriptPath))
        {
            string parentCandidate = Path.GetFullPath(Path.Combine(addonDir, "..", "swofty_helper.py"));
            if (File.Exists(parentCandidate))
                scriptPath = parentCandidate;
        }

        string[] candidates = new string[] {
            Path.Combine(addonDir, ".venv", "Scripts", "python.exe"),
            Path.Combine(addonDir, "runtime", "python.exe"),
            Path.Combine(addonDir, "..", ".venv", "Scripts", "python.exe"),
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

        string workDir = Path.GetDirectoryName(scriptPath);
        if (!string.IsNullOrEmpty(workDir) && Directory.Exists(workDir))
            Directory.SetCurrentDirectory(workDir);

        string argLine = "-u " + QuoteArg(scriptPath);
        for (int i = 0; i < args.Length; i++)
            argLine += " " + QuoteArg(args[i]);

        ProcessStartInfo psi = new ProcessStartInfo
        {
            FileName = pythonExe,
            Arguments = argLine,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using (Process proc = Process.Start(psi))
        {
            if (proc == null)
                return 1;
            proc.WaitForExit();
            return proc.ExitCode;
        }
    }
}
