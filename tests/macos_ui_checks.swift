import Foundation

@main
struct MacOSUIChecks {
    @MainActor
    static func main() async throws {
        guard let rawPort = ProcessInfo.processInfo.environment["LITEPARSE_TEST_PORT"],
              let port = Int(rawPort) else { fatalError("missing test port") }

        precondition(PipelineMode.hdScan.rawValue == "hd_scan")
        precondition(PipelineMode.vector.rawValue == "vector_pdf2zh")
        precondition(PipelineMode.hdScan.requestValue == "scanned")
        precondition(PipelineMode.vector.requestValue == "vector")
        precondition(PipelineMode.auto.requestValue == "auto")
        precondition(PipelineMode.inSitu.requestValue == "insitu_legacy")

        let manager = BackendManager(serverPort: port, startPolling: false)
        manager.refreshTasks()
        try await waitFor { manager.tasks.count == 1 }
        precondition(manager.tasks[0].status == .completed)
        manager.clearCompleted()
        manager.refreshTasks()
        try await Task.sleep(nanoseconds: 300_000_000)
        precondition(manager.tasks.isEmpty, "dismissed task returned after polling")

        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("liteparse-ui-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let first = directory.appendingPathComponent("one.pdf")
        let second = directory.appendingPathComponent("two.pdf")
        try Data("%PDF-1.4 test".utf8).write(to: first)
        try Data("%PDF-1.4 test".utf8).write(to: second)

        manager.selectedPipeline = .vector
        manager.selectedService = .google
        manager.handleDroppedURLs([first, second])
        precondition(manager.isUploading)
        manager.selectedPipeline = .hdScan
        manager.selectedService = .bing
        try await waitFor { !manager.isUploading }
        precondition(manager.errorMessage?.contains("1 份未能添加") == true)
        precondition(manager.errorMessage?.contains("two.pdf") == true)
        precondition(manager.errorMessage?.contains("HTTP 400") == true)

        manager.handleDroppedURLs([directory.appendingPathComponent("missing.txt")])
        precondition(manager.errorMessage?.contains("未找到") == true)
        print("macOS UI model checks passed")
    }

    @MainActor
    static func waitFor(_ condition: () -> Bool) async throws {
        for _ in 0..<100 {
            if condition() { return }
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        fatalError("timed out waiting for UI state")
    }
}
