import SwiftUI
import AppKit

@available(macOS 26.0, *)
@main
struct JParseApp: App {
    var body: some Scene {
        WindowGroup {
            MainContentView()
                .preferredColorScheme(.light)
                .background(LightTheme.canvasBg)
        }
        .windowStyle(.hiddenTitleBar)
        .windowBackgroundDragBehavior(.enabled)
        .defaultSize(width: 1000, height: 760)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("工作台") {
                Button("打开投递箱 (Inbox)") {
                    BackendManager.shared.revealInbox()
                }
                .keyboardShortcut("i", modifiers: [.command, .shift])

                Button("打开成果目录 (Outbox)") {
                    BackendManager.shared.revealOutbox()
                }
                .keyboardShortcut("o", modifiers: [.command, .shift])

                Divider()

                Button("刷新任务列表") {
                    BackendManager.shared.refreshTasks()
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("清除已完成任务") {
                    BackendManager.shared.clearCompleted()
                }
                .keyboardShortcut("k", modifiers: [.command])
            }
        }

        Settings {
            SettingsView()
        }
    }
}
