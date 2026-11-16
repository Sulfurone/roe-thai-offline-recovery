using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class PortableServer
{
    private const string Folder = "ROE-Thai-Offline";
    private const string Manifest = "portable-manifest.json";
    private const string Runtime = "runtime/python/pythonw.exe";
    private const string Interface = "server_ui.py";
    private const string Title = "ROE Thai Offline Server";

    private sealed class Receipt
    {
        public Dictionary<string, string> files { get; set; }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        bool installOnly = args.Length == 1 && args[0] == "--install-only";
        try
        {
            if (args.Length != 0 && !installOnly)
                throw new ArgumentException("Usage: run the EXE or pass --install-only.");

            Assembly assembly = Assembly.GetExecutingAssembly();
            string parent = Path.GetDirectoryName(assembly.Location);
            string installation;
            using (Stream payload = assembly.GetManifestResourceStream("portable.zip"))
            using (var archive = new ZipArchive(payload, ZipArchiveMode.Read))
                installation = Install(parent, archive);

            if (installOnly)
                return 0;

            if (!File.Exists(Path.Combine(installation, "32838", "Europa_Client.exe")))
                MessageBox.Show(
                    "请把你自己的原版泰服 32838 文件夹放在以下目录，再从服务端界面校验文件。\n\n"
                    + "Place your original Thai 32838 client folder inside this directory, then verify files in the app.\n\n"
                    + installation, Title, MessageBoxButtons.OK, MessageBoxIcon.Information);

            var start = new ProcessStartInfo
            {
                FileName = PackagePath(installation, Runtime),
                Arguments = "-I -B -X utf8 server_ui.py",
                WorkingDirectory = installation,
                UseShellExecute = false
            };
            using (Process process = Process.Start(start)) { }
            return 0;
        }
        catch (Exception error)
        {
            if (!installOnly)
                MessageBox.Show("无法打开服务端 / Unable to open the server.\n\n" + error.Message,
                                Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static string Install(string parent, ZipArchive archive)
    {
        string manifestJson;
        using (Stream stream = archive.GetEntry(Folder + "/" + Manifest).Open())
        using (var reader = new StreamReader(stream))
            manifestJson = reader.ReadToEnd();
        Receipt receipt = new JavaScriptSerializer().Deserialize<Receipt>(manifestJson);
        if (receipt == null || receipt.files == null || !receipt.files.ContainsKey(Runtime)
                || !receipt.files.ContainsKey(Interface))
            throw new InvalidDataException("The embedded portable manifest is incomplete.");

        string manifestHash;
        using (Stream stream = archive.GetEntry(Folder + "/" + Manifest).Open())
            manifestHash = Digest(stream);
        string target = Path.Combine(parent, Folder);
        if (Directory.Exists(target) || File.Exists(target))
        {
            if (Matches(target, manifestHash, receipt.files))
                return target;
            target = Path.Combine(parent, Folder + "-" + manifestHash.Substring(0, 8));
            if (Directory.Exists(target) || File.Exists(target))
            {
                if (Matches(target, manifestHash, receipt.files))
                    return target;
                throw new IOException("请将 EXE 移到新的可写目录。Move the EXE to a new writable folder.\n" + target);
            }
        }

        string staging = Path.Combine(parent, Folder + ".install-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        try
        {
            Unpack(archive, staging, Manifest);
            foreach (string relative in receipt.files.Keys)
                Unpack(archive, staging, relative);
            if (!Matches(staging, manifestHash, receipt.files))
                throw new InvalidDataException("Extracted files failed verification.");
            try
            {
                Directory.Move(staging, target);
            }
            catch (IOException)
            {
                if (!Matches(target, manifestHash, receipt.files))
                    throw;
            }
            return target;
        }
        finally
        {
            if (Directory.Exists(staging) && Path.GetDirectoryName(Path.GetFullPath(staging)) == parent)
                Directory.Delete(staging, true);
        }
    }

    private static void Unpack(ZipArchive archive, string folder, string relative)
    {
        ZipArchiveEntry entry = archive.GetEntry(PortableServer.Folder + "/" + relative);
        if (entry == null)
            throw new InvalidDataException("Missing package member: " + relative);
        string destination = PackagePath(folder, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(destination));
        entry.ExtractToFile(destination, false);
    }

    private static bool Matches(string folder, string manifestHash, Dictionary<string, string> files)
    {
        if (!Directory.Exists(folder) || !MatchesFile(folder, Manifest, manifestHash))
            return false;
        foreach (KeyValuePair<string, string> item in files)
            if (!MatchesFile(folder, item.Key, item.Value))
                return false;
        return true;
    }

    private static bool MatchesFile(string folder, string relative, string expectedHash)
    {
        string path = PackagePath(folder, relative);
        if (!File.Exists(path))
            return false;
        // The original client and the save/log folders are outside the manifest.
        // Manifest files and directories must be ordinary paths before reuse.
        string parent = path;
        while (true)
        {
            if ((File.GetAttributes(parent) & FileAttributes.ReparsePoint) != 0)
                return false;
            if (String.Equals(parent, folder, StringComparison.OrdinalIgnoreCase))
                break;
            parent = Path.GetDirectoryName(parent);
        }
        using (Stream stream = File.OpenRead(path))
            return String.Equals(Digest(stream), expectedHash, StringComparison.OrdinalIgnoreCase);
    }

    private static string PackagePath(string folder, string relative)
    {
        foreach (string name in relative.Split('/'))
            if (name.Length == 0 || name == "." || name == ".." || name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
                throw new InvalidDataException("Invalid package path: " + relative);
        return Path.Combine(folder, relative.Replace('/', Path.DirectorySeparatorChar));
    }

    private static string Digest(Stream source)
    {
        using (SHA256 hash = SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(source)).Replace("-", "").ToLowerInvariant();
    }
}
