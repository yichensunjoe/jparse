import Foundation
import SwiftUI
import AppKit

@MainActor
public final class BackendManager: ObservableObject {
    public static let shared = BackendManager()

    @Published public var connectionStatus: BackendConnectionStatus = .disconnected
    @Published public var tasks: [TaskItem] = []
    @Published public var selectedPipeline: PipelineMode = .auto {
        didSet { AppSettings.shared.defaultPipeline = selectedPipeline }
    }
    @Published public var selectedService: TranslationService = .bing {
        didSet { AppSettings.shared.defaultService = selectedService }
    }
    @Published public var isUploading: Bool = false
    @Published public var uploadStatusMessage: String = ""
    @Published public var errorMessage: String? = nil
    @Published public private(set) var isSyncingOutputFolder: Bool = false
    @Published public private(set) var outputFolderError: String? = nil

    private var pollTimer: Timer?
    private var backendProcess: Process?
    private var lastSyncedOutputFolder: String?
    private var dismissedCompletedIDs: Set<String> = []
    public let serverPort: Int
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

    public var defaultOutboxPath: String {
        (projectRootPath as NSString).appendingPathComponent("outbox")
    }

    public var outputFolderPath: String {
        let custom = AppSettings.shared.outputFolderPath.trimmingCharacters(in: .whitespacesAndNewlines)
        return custom.isEmpty ? defaultOutboxPath : custom
    }

    public var outputFolderDisplayPath: String {
        (outputFolderPath as NSString).abbreviatingWithTildeInPath
    }

    public var isUsingCustomOutputFolder: Bool {
        !AppSettings.shared.outputFolderPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public init(serverPort: Int = 8765, startPolling: Bool = true) {
        self.serverPort = serverPort
        // 恢复上次的设置；首次启动保持项目默认 outbox。
        selectedPipeline = AppSettings.shared.defaultPipeline
        selectedService = AppSettings.shared.defaultService
        if startPolling { self.startPolling() }
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
                    // 输出目录只存在 App 的 UserDefaults 里；每次连上/重连后
                    // 都要重放给后台，后台重启也不会悄悄回到旧目录。
                    syncOutputFolderIfNeeded()
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
        lastSyncedOutputFolder = nil
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
                    self.connectionStatus = .disconnected
                    self.lastSyncedOutputFolder = nil
                    return
                }
                let decoder = JSONDecoder()
                let fetchedTasks = try decoder.decode([TaskItem].self, from: data)
                self.dismissedCompletedIDs.formIntersection(Set(fetchedTasks.map(\.id)))
                let visibleTasks = fetchedTasks.filter { !self.dismissedCompletedIDs.contains($0.id) }
                // 等值不发布，避免每秒轮询时滚动条反复抖动。
                if visibleTasks != self.tasks {
                    self.tasks = visibleTasks
                }
                if case .connected = self.connectionStatus {
                    // stays connected
                } else {
                    self.connectionStatus = .connected(port: self.serverPort)
                }
                self.syncOutputFolderIfNeeded()
            } catch {
                self.connectionStatus = .disconnected
                self.lastSyncedOutputFolder = nil
            }
        }
    }

    // MARK: - File Drag & Upload Processing

    public func handleDroppedURLs(_ urls: [URL]) {
        guard !isUploading else {
            errorMessage = "正在添加上一批文献，请完成后再导入。"
            return
        }
        let pdfs = collectPDFs(from: urls)
        guard !pdfs.isEmpty else {
            errorMessage = "未找到可处理的 PDF 文档。请拖入 .pdf 文件或包含 PDF 的文件夹。"
            return
        }

        let pipeline = selectedPipeline
        let service = selectedService
        errorMessage = nil
        isUploading = true
        uploadStatusMessage = "正在添加 \(pdfs.count) 份文献…"

        Task {
            var failures: [String] = []
            for (idx, pdfURL) in pdfs.enumerated() {
                uploadStatusMessage = "正在添加 \(idx + 1)/\(pdfs.count)：\(pdfURL.lastPathComponent)"
                if let reason = await uploadSinglePDF(url: pdfURL, pipeline: pipeline, service: service) {
                    failures.append("\(pdfURL.lastPathComponent)：\(reason)")
                }
            }

            self.isUploading = false
            if !failures.isEmpty {
                self.errorMessage = "已添加 \(pdfs.count - failures.count) 份，\(failures.count) 份未能添加：\n" + failures.joined(separator: "\n")
            }
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

    private func uploadSinglePDF(url: URL, pipeline: PipelineMode, service: TranslationService) async -> String? {
        let uploadURL = serverBaseURL.appendingPathComponent("api/upload")
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "POST"
        request.timeoutInterval = 60.0

        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        guard let fileData = try? Data(contentsOf: url) else {
            return "无法读取文件"
        }

        var body = Data()

        // 1. pipelineMode
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"pipelineMode\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(pipeline.requestValue)\r\n".data(using: .utf8)!)

        // 2. service
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"service\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(service.rawValue)\r\n".data(using: .utf8)!)

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
            guard let httpResp = response as? HTTPURLResponse else { return "后台响应无效" }
            guard httpResp.statusCode == 200 else { return "后台拒绝了文件（HTTP \(httpResp.statusCode)）" }
            return nil
        } catch {
            return "无法连接后台：\(error.localizedDescription)"
        }
    }

    // MARK: - Actions & Finder Integration

    public func revealOutbox() {
        revealDirectory(at: outputFolderPath)
    }

    public func revealInbox() {
        revealDirectory(at: (projectRootPath as NSString).appendingPathComponent("inbox"))
    }

    /// Open a directory exactly once, and only after making sure it exists.
    ///
    /// Previously these methods posted to /api/reveal_* (which runs `open` on
    /// the backend) *and* called NSWorkspace locally, so one click produced two
    /// Finder windows.
    private func revealDirectory(at path: String) {
        let url = URL(fileURLWithPath: path)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        guard FileManager.default.fileExists(atPath: url.path) else { return }
        NSWorkspace.shared.open(url)
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
        dismissedCompletedIDs.formUnion(tasks.filter { $0.status == .completed }.map(\.id))
        tasks.removeAll(where: { $0.status == .completed })
    }

    // MARK: - Output Folder

    /// 把 App 里保存的输出目录同步给后台。`force` 用于用户在设置里
    /// 明确点选/恢复默认后立即生效；普通轮询会按路径去重。
    public func syncOutputFolderIfNeeded(force: Bool = false) {
        guard connectionStatus.isConnected else { return }

        let target = outputFolderPath
        guard force || lastSyncedOutputFolder != target else { return }
        guard !isSyncingOutputFolder else { return }

        isSyncingOutputFolder = true
        outputFolderError = nil

        var request = URLRequest(url: serverBaseURL.appendingPathComponent("api/settings"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 8.0

        do {
            request.httpBody = try JSONSerialization.data(
                withJSONObject: ["outbox_dir": target],
                options: []
            )
        } catch {
            isSyncingOutputFolder = false
            outputFolderError = "无法编码输出文件夹设置：\(error.localizedDescription)"
            return
        }

        Task {
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200 else {
                    throw OutputFolderError.backendRejected
                }
                _ = try JSONDecoder().decode(BackendSettingsResponse.self, from: data)

                self.lastSyncedOutputFolder = target
                self.isSyncingOutputFolder = false
                self.outputFolderError = nil

                // 用户在请求飞行期间又换了目录：继续追平最新选择。
                if self.outputFolderPath != target {
                    self.syncOutputFolderIfNeeded(force: true)
                }
            } catch {
                self.isSyncingOutputFolder = false
                self.outputFolderError = "无法应用输出文件夹：\(error.localizedDescription)"
            }
        }
    }

    private struct BackendSettingsResponse: Decodable {
        let outbox_dir: String
    }

    private enum OutputFolderError: LocalizedError {
        case backendRejected

        var errorDescription: String? {
            switch self {
            case .backendRejected:
                return "后台拒绝了该文件夹（请确认目录存在且可写）"
            }
        }
    }
}
