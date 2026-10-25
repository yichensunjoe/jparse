import Foundation
import SwiftUI
import AppKit

@MainActor
public final class BackendManager: ObservableObject {
    public static let shared = BackendManager()

    @Published public var connectionStatus: BackendConnectionStatus = .disconnected
    @Published public var tasks: [TaskItem] = []
    @Published public var selectedPipeline: PipelineMode = .auto
    @Published public var selectedService: TranslationService = .bing
    @Published public var isUploading: Bool = false
    @Published public var uploadStatusMessage: String = ""
    @Published public var errorMessage: String? = nil

    private var pollTimer: Timer?
    private var backendProcess: Process?
    public let serverPort: Int = 8765
    public var serverBaseURL: URL {
        URL(string: "http://127.0.0.1:\(serverPort)")!
    }

    public var projectRootPath: String {
        // Detect workspace root or parent of executable
        let currentDir = FileManager.default.currentDirectoryPath
        if FileManager.default.fileExists(atPath: (currentDir as NSString).appendingPathComponent("src/web_app.py")) {
            return currentDir
        }
        // Fallback to configured project path
        let hardcodedPath = "/Users/joe/ai/reasonix/projects/active/P052-LiteParse-PDF自动识别"
        if FileManager.default.fileExists(atPath: hardcodedPath) {
            return hardcodedPath
        }
        return currentDir
    }

    public init() {
        startPolling()
    }

    deinit {
        pollTimer?.invalidate()
        backendProcess?.terminate()
    }

    // MARK: - Lifecycle & Connection

    public func startPolling() {
        checkBackendHealth()
        pollTimer?.invalidate()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.refreshTasks()
            }
        }
    }

    public func stopPolling() {
        pollTimer?.invalidate()
        pollTimer = nil
    }

    public func checkBackendHealth() {
        let endpoint = serverBaseURL.appendingPathComponent("api/tasks")
        var request = URLRequest(url: endpoint)
        request.timeoutInterval = 1.5

        Task {
            do {
                let (_, response) = try await URLSession.shared.data(for: request)
                if let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200 {
                    if connectionStatus != .connected(port: serverPort) {
                        connectionStatus = .connected(port: serverPort)
                    }
                    refreshTasks()
                } else {
                    handleConnectionFailure()
                }
            } catch {
                handleConnectionFailure()
            }
        }
    }

    private func handleConnectionFailure() {
        if case .connected = connectionStatus {
            connectionStatus = .disconnected
        }
        // Auto-launch local python server if not running
        launchPythonBackendIfNeeded()
    }

    public func launchPythonBackendIfNeeded() {
        guard backendProcess == nil || !backendProcess!.isRunning else { return }

        connectionStatus = .connecting

        let proc = Process()
        let root = projectRootPath
        proc.currentDirectoryURL = URL(fileURLWithPath: root)

        // Try Python interpreters
        let candidatePythons = [
            "/Users/joe/.local/share/agent-tools/bin/python3",
            "/usr/bin/python3",
            "/opt/homebrew/bin/python3",
            "python3"
        ]

        var selectedPython = "/usr/bin/python3"
        for p in candidatePythons {
            if FileManager.default.fileExists(atPath: p) {
                selectedPython = p
                break
            }
        }

        proc.executableURL = URL(fileURLWithPath: selectedPython)
        proc.arguments = [
            "-m", "src.web_app",
            "\(serverPort)",
            "--no-browser",
            "--no-open"
        ]

        // Set enriched PATH and JAVA_HOME environment so child tools (like Java and OpenDataLoader) work seamlessly
        var env = ProcessInfo.processInfo.environment
        let extraPaths = [
            "/Users/joe/.local/bin",
            "/opt/homebrew/bin",
            "/opt/homebrew/opt/openjdk/bin",
            "/usr/local/bin"
        ]
        let currentPath = env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        env["PATH"] = (extraPaths + [currentPath]).joined(separator: ":")
        if FileManager.default.fileExists(atPath: "/opt/homebrew/opt/openjdk") {
            env["JAVA_HOME"] = "/opt/homebrew/opt/openjdk"
        }
        proc.environment = env

        // Discard stdout/stderr using nullDevice so process never blocks on unread pipe buffers
        proc.standardOutput = FileHandle.nullDevice
        proc.standardError = FileHandle.nullDevice

        do {
            try proc.run()
            self.backendProcess = proc
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) { [weak self] in
                self?.checkBackendHealth()
            }
        } catch {
            self.connectionStatus = .error("无法启动后台服务: \(error.localizedDescription)")
        }
    }

    // MARK: - Task Fetching

    public func refreshTasks() {
        let endpoint = serverBaseURL.appendingPathComponent("api/tasks")
        var request = URLRequest(url: endpoint)
        request.timeoutInterval = 2.0

        Task {
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200 else {
                    return
                }
                let decoder = JSONDecoder()
                let fetchedTasks = try decoder.decode([TaskItem].self, from: data)
                self.tasks = fetchedTasks
                if case .connected = self.connectionStatus {
                    // stays connected
                } else {
                    self.connectionStatus = .connected(port: self.serverPort)
                }
            } catch {
                // If fetching tasks failed, ping health
            }
        }
    }

    // MARK: - File Drag & Upload Processing

    public func handleDroppedURLs(_ urls: [URL]) {
        let pdfs = collectPDFs(from: urls)
        guard !pdfs.isEmpty else {
            errorMessage = "未找到可处理的 PDF 文档。请拖入 .pdf 文件或包含 PDF 的文件夹。"
            return
        }

        errorMessage = nil
        isUploading = true
        uploadStatusMessage = "正在批量添加 \(pdfs.count) 份文献..."

        Task {
            var successCount = 0
            for (idx, pdfURL) in pdfs.enumerated() {
                uploadStatusMessage = "[\(idx + 1)/\(pdfs.count)] 正在投递 \(pdfURL.lastPathComponent)..."
                let success = await uploadSinglePDF(url: pdfURL)
                if success {
                    successCount += 1
                }
            }

            self.isUploading = false
            self.uploadStatusMessage = "已成功添加 \(successCount) 份文献至转换队列"
            self.refreshTasks()
        }
    }

    public func collectPDFs(from urls: [URL]) -> [URL] {
        var results: [URL] = []
        for url in urls {
            var isDir: ObjCBool = false
            if FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir) {
                if isDir.boolValue {
                    // Recursive directory traversal
                    if let enumerator = FileManager.default.enumerator(
                        at: url,
                        includingPropertiesForKeys: [.isRegularFileKey],
                        options: [.skipsHiddenFiles]
                    ) {
                        for case let fileURL as URL in enumerator {
                            if fileURL.pathExtension.lowercased() == "pdf" {
                                results.append(fileURL)
                            }
                        }
                    }
                } else if url.pathExtension.lowercased() == "pdf" {
                    results.append(url)
                }
            }
        }
        return results
    }

    private func uploadSinglePDF(url: URL) async -> Bool {
        let uploadURL = serverBaseURL.appendingPathComponent("api/upload")
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "POST"
        request.timeoutInterval = 60.0

        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        guard let fileData = try? Data(contentsOf: url) else {
            return false
        }

        var body = Data()

        // 1. pipelineMode
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"pipelineMode\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(selectedPipeline.rawValue)\r\n".data(using: .utf8)!)

        // 2. service
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"service\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(selectedService.rawValue)\r\n".data(using: .utf8)!)

        // 3. relativePath
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"relativePath\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(url.lastPathComponent)\r\n".data(using: .utf8)!)

        // 4. file
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(url.lastPathComponent)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/pdf\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n".data(using: .utf8)!)

        // End delimiter
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        do {
            let (_, response) = try await URLSession.shared.upload(for: request, from: body)
            if let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200 {
                return true
            }
        } catch {
            print("Upload failed: \(error.localizedDescription)")
        }
        return false
    }

    // MARK: - Actions & Finder Integration

    public func revealOutbox() {
        let endpoint = serverBaseURL.appendingPathComponent("api/reveal_outbox")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        Task {
            _ = try? await URLSession.shared.data(for: request)
        }
        // Also fallback to local Finder open
        let outboxPath = (projectRootPath as NSString).appendingPathComponent("outbox")
        NSWorkspace.shared.open(URL(fileURLWithPath: outboxPath))
    }

    public func revealInbox() {
        let endpoint = serverBaseURL.appendingPathComponent("api/reveal_inbox")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        Task {
            _ = try? await URLSession.shared.data(for: request)
        }
        let inboxPath = (projectRootPath as NSString).appendingPathComponent("inbox")
        NSWorkspace.shared.open(URL(fileURLWithPath: inboxPath))
    }

    public func openFile(path: String) {
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.open(url)
    }

    public func revealInFinder(path: String) {
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    public func copyPath(path: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(path, forType: .string)
    }

    public func clearCompleted() {
        tasks.removeAll(where: { $0.status == .completed })
    }
}
