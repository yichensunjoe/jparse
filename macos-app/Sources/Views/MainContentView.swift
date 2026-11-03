import SwiftUI

public struct MainContentView: View {
    @StateObject private var manager = BackendManager.shared
    @ObservedObject private var settings = AppSettings.shared

    public init() {}

    public var body: some View {
        LightContentView(manager: manager)
            // LightTheme 的色板是静态令牌；切换主题时用 revision
            // 让整棵树重新取值，避免只有设置窗口变色。
            .id(settings.themeRevision)
            .frame(minWidth: 900, minHeight: 640)
            .background(LightTheme.canvasBg)
    }
}
