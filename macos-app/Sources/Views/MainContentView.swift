import SwiftUI

public struct MainContentView: View {
    @StateObject private var manager = BackendManager.shared

    public init() {}

    public var body: some View {
        LightContentView(manager: manager)
            .frame(minWidth: 900, minHeight: 640)
            .background(LightTheme.canvasBg)
    }
}
