import SwiftUI

public struct MainContentView: View {
    @StateObject private var manager = BackendManager.shared

    public init() {}

    public var body: some View {
        HStack(spacing: 0) {
            SwissSidebarView(manager: manager)
            SwissMainView(manager: manager)
        }
        .frame(minWidth: 940, minHeight: 660)
        .background(SwissTheme.canvasBg)
    }
}
