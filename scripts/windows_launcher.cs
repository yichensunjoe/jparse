// .NET Framework is included in Windows 10/11; the application payload is
// appended to this small launcher during the Windows CI build.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class JParseLauncher
{
    private const int TrailerSize = 56; // SHA256 + uint64 length + 16-byte magic
    private static readonly byte[] Magic = Encoding.ASCII.GetBytes("JPARSE-EXE-V1!!!");

    [STAThread]
    private static int Main(string[] args)
    {
        bool headless = Array.IndexOf(args, "--server-only") >= 0;
        if (headless)
        {
            try { PrepareAndStart(args); return 0; }
            catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        }

        Application.EnableVisualStyles();
        Form splash = new Form();
        splash.Text = "JParse";
        splash.StartPosition = FormStartPosition.CenterScreen;
        splash.FormBorderStyle = FormBorderStyle.FixedDialog;
        splash.MaximizeBox = false;
        splash.MinimizeBox = false;
        splash.ClientSize = new Size(450, 95);
        Label label = new Label();
        label.Text = "正在准备 JParse，首次启动可能需要几分钟……";
        label.AutoSize = true;
        label.Location = new Point(25, 20);
        ProgressBar progress = new ProgressBar();
        progress.Location = new Point(25, 50);
        progress.Size = new Size(400, 17);
        progress.Style = ProgressBarStyle.Marquee;
        splash.Controls.Add(label);
        splash.Controls.Add(progress);
        int result = 0;
        splash.Shown += delegate {
            Thread worker = new Thread(delegate() {
                try { PrepareAndStart(args); }
                catch (Exception ex) {
                    result = 1;
                    MessageBox.Show("JParse 启动失败：\n" + ex.Message, "JParse", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                finally { if (!splash.IsDisposed) splash.BeginInvoke(new Action(splash.Close)); }
            });
            worker.IsBackground = true;
            worker.Start();
        };
        Application.Run(splash);
        return result;
    }

    private static void PrepareAndStart(string[] args)
    {
        string exe = Process.GetCurrentProcess().MainModule.FileName;
        string baseDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "JParse");
        Directory.CreateDirectory(baseDir);
        string runtime;
        using (FileStream input = File.OpenRead(exe))
        {
            if (input.Length < TrailerSize) throw new InvalidDataException("程序包不完整。");
            input.Seek(-TrailerSize, SeekOrigin.End);
            byte[] expectedHash = new byte[32];
            ReadExactly(input, expectedHash, 0, expectedHash.Length);
            byte[] sizeBytes = new byte[8];
            ReadExactly(input, sizeBytes, 0, sizeBytes.Length);
            long size = BitConverter.ToInt64(sizeBytes, 0);
            byte[] magic = new byte[16];
            ReadExactly(input, magic, 0, magic.Length);
            if (!Equal(magic, Magic) || size <= 0 || size > input.Length - TrailerSize)
                throw new InvalidDataException("程序包头部无效。");
            string key = BitConverter.ToString(expectedHash).Replace("-", "").ToLowerInvariant();
            string runtimes = Path.Combine(baseDir, "runtimes");
            Directory.CreateDirectory(runtimes);
            runtime = Path.Combine(runtimes, key);
            using (Mutex gate = new Mutex(false, "Local\\JParse-" + key))
            {
                bool acquired = false;
                try {
                    try { acquired = gate.WaitOne(TimeSpan.FromMinutes(10)); }
                    catch (AbandonedMutexException) { acquired = true; }
                    if (!acquired) throw new IOException("等待 JParse 初始化超时。");
                    if (!RuntimeReady(runtime))
                        ExtractRuntime(input, size, expectedHash, runtimes, runtime);
                }
                finally { if (acquired) gate.ReleaseMutex(); }
            }
        }
        string data = Environment.GetEnvironmentVariable("JPARSE_DATA_DIR");
        if (String.IsNullOrWhiteSpace(data)) data = Path.Combine(baseDir, "data");
        Directory.CreateDirectory(data);
        string pythonDir = Path.Combine(runtime, "python");
        string pythonw = Path.Combine(pythonDir, "pythonw.exe");
        string script = Path.Combine(runtime, "project", "src", "desktop_app_windows.py");
        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = pythonw;
        start.WorkingDirectory = Path.Combine(runtime, "project");
        StringBuilder arguments = new StringBuilder(Quote(script));
        foreach (string arg in args) arguments.Append(" ").Append(Quote(arg));
        start.Arguments = arguments.ToString();
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        start.EnvironmentVariables["JPARSE_DATA_DIR"] = data;
        start.EnvironmentVariables["JPARSE_BUNDLED_PYTHON"] = Path.Combine(pythonDir, "python.exe");
        start.EnvironmentVariables["JPARSE_LAYOUT_MODEL"] = Path.Combine(runtime, "models", "layout.onnx");
        start.EnvironmentVariables["NOTO_FONT_PATH"] = Path.Combine(runtime, "models", "SourceHanSerifCN-Regular.ttf");
        start.EnvironmentVariables["PYTHONUTF8"] = "1";
        start.EnvironmentVariables["JAVA_HOME"] = Path.Combine(runtime, "jre");
        start.EnvironmentVariables["PATH"] = Path.Combine(runtime, "jre", "bin") + ";" + pythonDir + ";" + Environment.GetEnvironmentVariable("PATH");
        if (Process.Start(start) == null) throw new IOException("无法启动内置 Python。");
    }

    private static bool RuntimeReady(string dir)
    {
        return File.Exists(Path.Combine(dir, ".complete")) &&
            File.Exists(Path.Combine(dir, "python", "python.exe")) &&
            File.Exists(Path.Combine(dir, "python", "pythonw.exe")) &&
            File.Exists(Path.Combine(dir, "project", "src", "desktop_app_windows.py")) &&
            File.Exists(Path.Combine(dir, "jre", "bin", "java.exe")) &&
            File.Exists(Path.Combine(dir, "models", "layout.onnx")) &&
            File.Exists(Path.Combine(dir, "models", "SourceHanSerifCN-Regular.ttf"));
    }

    private static void ExtractRuntime(FileStream input, long size, byte[] expectedHash, string parent, string destination)
    {
        string temp = Path.Combine(parent, ".extract-" + Guid.NewGuid().ToString("N"));
        string archivePath = temp + ".zip";
        Directory.CreateDirectory(temp);
        try {
            input.Seek(-TrailerSize - size, SeekOrigin.End);
            using (SHA256 sha = SHA256.Create())
            using (FileStream output = File.Create(archivePath))
            {
                byte[] buffer = new byte[1024 * 1024];
                long remaining = size;
                while (remaining > 0) {
                    int count = input.Read(buffer, 0, (int)Math.Min(buffer.Length, remaining));
                    if (count == 0) throw new EndOfStreamException("程序包已损坏。");
                    output.Write(buffer, 0, count);
                    sha.TransformBlock(buffer, 0, count, buffer, 0);
                    remaining -= count;
                }
                sha.TransformFinalBlock(new byte[0], 0, 0);
                if (!Equal(sha.Hash, expectedHash)) throw new InvalidDataException("程序包校验失败。");
            }
            string prefix = Path.GetFullPath(temp).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            using (ZipArchive zip = ZipFile.OpenRead(archivePath)) {
                foreach (ZipArchiveEntry entry in zip.Entries) {
                    string target = Path.GetFullPath(Path.Combine(temp, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                    if (!target.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("程序包含无效路径。");
                    if (String.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(target); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    entry.ExtractToFile(target);
                }
            }
            File.WriteAllText(Path.Combine(temp, ".complete"), "ok");
            if (!RuntimeReady(temp)) throw new InvalidDataException("程序包缺少必要组件。");
            if (Directory.Exists(destination)) Directory.Delete(destination, true);
            Directory.Move(temp, destination);
        }
        finally {
            if (File.Exists(archivePath)) File.Delete(archivePath);
            if (Directory.Exists(temp)) Directory.Delete(temp, true);
        }
    }

    private static bool Equal(byte[] a, byte[] b)
    {
        if (a.Length != b.Length) return false;
        int diff = 0;
        for (int i = 0; i < a.Length; i++) diff |= a[i] ^ b[i];
        return diff == 0;
    }

    private static void ReadExactly(Stream stream, byte[] buffer, int offset, int count)
    {
        while (count > 0) {
            int n = stream.Read(buffer, offset, count);
            if (n == 0) throw new EndOfStreamException();
            offset += n;
            count -= n;
        }
    }

    private static string Quote(string argument)
    {
        // Windows command-line escaping, including backslashes before quotes/end.
        StringBuilder result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in argument) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') {
                result.Append('\\', slashes * 2 + 1);
                result.Append(c);
            } else {
                result.Append('\\', slashes);
                result.Append(c);
            }
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }
}
