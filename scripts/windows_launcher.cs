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
            catch (Exception ex) { RecordFailure(ex); Console.Error.WriteLine(ex); return 1; }
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
                    RecordFailure(ex);
                    string stage = ex.Data["JParseStage"] as string;
                    string detail = String.IsNullOrEmpty(stage) ? "" : "（" + stage + "）";
                    string guidance = ex is UnauthorizedAccessException
                        ? "\n请确认当前账户可以在本用户的 JParse 文件夹中创建和写入文件。"
                        : "";
                    MessageBox.Show("JParse 启动失败" + detail + "：\n" + ex.Message + guidance,
                        "JParse", MessageBoxButtons.OK, MessageBoxIcon.Error);
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
        string runtimeId;
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
            runtimeId = key;
            // Keep the runtime path short enough for Windows installations
            // which still enforce the traditional MAX_PATH limit.
            string runtimes = Path.Combine(baseDir, "r");
            Directory.CreateDirectory(runtimes);
            using (FileStream gate = AcquireRuntimeLock(runtimes, key))
            {
                runtime = FindReadyRuntime(runtimes, key);
                if (runtime == null) {
                    runtime = FindIncompleteRuntime(runtimes, key);
                    if (runtime == null)
                        runtime = Path.Combine(runtimes, key.Substring(0, 12) + "-" + Guid.NewGuid().ToString("N").Substring(0, 8));
                    ExtractRuntime(input, size, expectedHash, runtimes, runtime);
                }
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
        StringBuilder arguments = new StringBuilder("-X utf8 ").Append(Quote(script));
        foreach (string arg in args) arguments.Append(" ").Append(Quote(arg));
        start.Arguments = arguments.ToString();
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        start.EnvironmentVariables["JPARSE_DATA_DIR"] = data;
        start.EnvironmentVariables["JPARSE_RUNTIME_ID"] = runtimeId;
        start.EnvironmentVariables["JPARSE_WATCH_INBOX"] = "1";
        start.EnvironmentVariables["JPARSE_BUNDLED_PYTHON"] = Path.Combine(pythonDir, "python.exe");
        start.EnvironmentVariables["JPARSE_PADDLE_PYTHON"] = Path.Combine(runtime, "ocr-python", "python.exe");
        start.EnvironmentVariables["PADDLE_PDX_CACHE_HOME"] = Path.Combine(runtime, "ocr-models");
        start.EnvironmentVariables["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True";
        start.EnvironmentVariables["JPARSE_LAYOUT_MODEL"] = Path.Combine(runtime, "models", "layout.onnx");
        start.EnvironmentVariables["JPARSE_FONT_DIR"] = Path.Combine(runtime, "models");
        start.EnvironmentVariables["NOTO_FONT_PATH"] = Path.Combine(runtime, "models", "SourceHanSerifCN-Regular.ttf");
        start.EnvironmentVariables["PYTHONUTF8"] = "1";
        start.EnvironmentVariables["JAVA_HOME"] = Path.Combine(runtime, "jre");
        start.EnvironmentVariables["PATH"] = Path.Combine(runtime, "jre", "bin") + ";" + pythonDir + ";" + Environment.GetEnvironmentVariable("PATH");
        if (Process.Start(start) == null) throw new IOException("无法启动内置 Python。");
    }

    private static FileStream AcquireRuntimeLock(string parent, string key)
    {
        string path = Path.Combine(parent, ".lock-" + key);
        Stopwatch wait = Stopwatch.StartNew();
        while (true) {
            try { return new FileStream(path, FileMode.OpenOrCreate, FileAccess.Write, FileShare.None); }
            catch (IOException ex) {
                int code = ex.HResult & 0xffff;
                if (code != 32 && code != 33) throw;
                if (wait.Elapsed >= TimeSpan.FromMinutes(10))
                    throw new IOException("等待 JParse 初始化超时。", ex);
                Thread.Sleep(200);
            }
        }
    }

    private static string FindReadyRuntime(string parent, string key)
    {
        string prefix = key.Substring(0, 12) + "-";
        foreach (string candidate in Directory.GetDirectories(parent, prefix + "*")) {
            try { if (RuntimeReady(candidate, key)) return candidate; }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        return null;
    }

    private static string FindIncompleteRuntime(string parent, string key)
    {
        string prefix = key.Substring(0, 12) + "-";
        foreach (string candidate in Directory.GetDirectories(parent, prefix + "*")) {
            try {
                string payload = Path.Combine(candidate, ".payload");
                if (File.Exists(payload) && String.Equals(File.ReadAllText(payload).Trim(), key, StringComparison.OrdinalIgnoreCase)
                    && !RuntimeReady(candidate, key)) return candidate;
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        return null;
    }

    private static bool RuntimeReady(string dir, string key)
    {
        string marker = Path.Combine(dir, ".complete");
        string payload = Path.Combine(dir, ".payload");
        return File.Exists(payload) && String.Equals(File.ReadAllText(payload).Trim(), key, StringComparison.OrdinalIgnoreCase) &&
            File.Exists(marker) && String.Equals(File.ReadAllText(marker).Trim(), key, StringComparison.OrdinalIgnoreCase) &&
            File.Exists(Path.Combine(dir, "python", "python.exe")) &&
            File.Exists(Path.Combine(dir, "python", "pythonw.exe")) &&
            File.Exists(Path.Combine(dir, "ocr-python", "python.exe")) &&
            Directory.Exists(Path.Combine(dir, "ocr-models", "official_models")) &&
            File.Exists(Path.Combine(dir, "project", "src", "desktop_app_windows.py")) &&
            File.Exists(Path.Combine(dir, "jre", "bin", "java.exe")) &&
            File.Exists(Path.Combine(dir, "models", "layout.onnx")) &&
            File.Exists(Path.Combine(dir, "models", "SourceHanSerifCN-Regular.ttf")) &&
            File.Exists(Path.Combine(dir, "models", "SourceHanSerifCN-Bold.ttf")) &&
            File.Exists(Path.Combine(dir, "models", "SourceHanSansCN-Regular.ttf")) &&
            File.Exists(Path.Combine(dir, "models", "SourceHanSansCN-Bold.ttf"));
    }

    private static void ExtractRuntime(FileStream input, long size, byte[] expectedHash, string parent, string destination)
    {
        string stage = "创建运行目录";
        bool created = false;
        bool payloadMarked = false;
        try {
            string key = BitConverter.ToString(expectedHash).Replace("-", "").ToLowerInvariant();
            string payloadMarker = Path.Combine(destination, ".payload");
            if (Directory.Exists(destination)) {
                if (!File.Exists(payloadMarker) || !String.Equals(File.ReadAllText(payloadMarker).Trim(), key, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("运行目录与当前程序包不匹配。");
                payloadMarked = true;
            } else {
                Directory.CreateDirectory(destination);
                created = true;
                File.WriteAllText(payloadMarker, key);
                payloadMarked = true;
            }
            // A restarted extraction must never appear complete until every
            // bundled file has been written again.
            File.WriteAllText(Path.Combine(destination, ".complete"), "incomplete");
            input.Seek(-TrailerSize - size, SeekOrigin.End);
            long payloadOffset = input.Position;
            stage = "校验程序包";
            using (SHA256 sha = SHA256.Create())
            {
                byte[] buffer = new byte[1024 * 1024];
                long remaining = size;
                while (remaining > 0) {
                    int count = input.Read(buffer, 0, (int)Math.Min(buffer.Length, remaining));
                    if (count == 0) throw new EndOfStreamException("程序包已损坏。");
                    sha.TransformBlock(buffer, 0, count, buffer, 0);
                    remaining -= count;
                }
                sha.TransformFinalBlock(new byte[0], 0, 0);
                if (!Equal(sha.Hash, expectedHash)) throw new InvalidDataException("程序包校验失败。");
            }
            stage = "展开运行文件";
            string prefix = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            using (Stream slice = new PayloadStream(input, payloadOffset, size))
            using (ZipArchive zip = new ZipArchive(slice, ZipArchiveMode.Read, false)) {
                foreach (ZipArchiveEntry entry in zip.Entries) {
                    string target = Path.GetFullPath(Path.Combine(destination, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                    if (!target.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("程序包含无效路径。");
                    if (String.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(target); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    entry.ExtractToFile(target, true);
                }
            }
            stage = "确认运行环境";
            File.WriteAllText(Path.Combine(destination, ".complete"), key);
            if (!RuntimeReady(destination, key)) throw new InvalidDataException("程序包缺少必要组件。");
        }
        catch (Exception ex) {
            ex.Data["JParseStage"] = stage;
            // Keep marked partial data for the next launch to overwrite and
            // reuse. This avoids requiring directory-delete permission and
            // prevents repeated failures from consuming another 2 GB each.
            if (created && !payloadMarked) {
                try { Directory.Delete(destination, true); }
                catch (Exception cleanup) { ex.Data["JParseCleanupFailure"] = cleanup.Message; }
            }
            throw;
        }
    }

    private static void RecordFailure(Exception error)
    {
        try {
            string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "JParse", "data", "logs");
            Directory.CreateDirectory(root);
            string log = Path.Combine(root, "launcher-bootstrap.log");
            string entry = DateTime.Now.ToString("s") + " 阶段=" + error.Data["JParseStage"] + " " + error +
                " 清理=" + error.Data["JParseCleanupFailure"] + Environment.NewLine;
            if (entry.Length > 8000) entry = entry.Substring(0, 8000) + Environment.NewLine;
            const long limit = 1024 * 1024;
            long existing = File.Exists(log) ? new FileInfo(log).Length : 0;
            if (existing + Encoding.UTF8.GetByteCount(entry) > limit) {
                string backup = log + ".1";
                if (File.Exists(backup)) File.Delete(backup);
                if (File.Exists(log)) File.Move(log, backup);
            }
            File.AppendAllText(log, entry, Encoding.UTF8);
        } catch (Exception) { /* Reporting must never hide the startup error. */ }
    }

    // Expose only the appended ZIP to ZipArchive without copying an 800 MB
    // temporary archive or requiring deletion rights to commit the runtime.
    private sealed class PayloadStream : Stream
    {
        private readonly Stream source;
        private readonly long start;
        private readonly long length;
        private long position;

        internal PayloadStream(Stream source, long start, long length)
        {
            this.source = source;
            this.start = start;
            this.length = length;
            Seek(0, SeekOrigin.Begin);
        }

        public override bool CanRead { get { return true; } }
        public override bool CanSeek { get { return true; } }
        public override bool CanWrite { get { return false; } }
        public override long Length { get { return length; } }
        public override long Position { get { return position; } set { Seek(value, SeekOrigin.Begin); } }

        public override int Read(byte[] buffer, int offset, int count)
        {
            int allowed = (int)Math.Min((long)count, length - position);
            int read = source.Read(buffer, offset, allowed);
            position += read;
            return read;
        }

        public override long Seek(long offset, SeekOrigin origin)
        {
            long next = origin == SeekOrigin.Begin ? offset :
                origin == SeekOrigin.Current ? position + offset : length + offset;
            if (next < 0 || next > length) throw new IOException("程序包读取位置无效。");
            source.Seek(start + next, SeekOrigin.Begin);
            position = next;
            return position;
        }

        public override void Flush() { }
        public override void SetLength(long value) { throw new NotSupportedException(); }
        public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
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
