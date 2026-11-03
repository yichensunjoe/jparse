import Foundation
import SwiftUI

// MARK: - Accent palette

public struct AccentPalette {
    public let base: Color
    public let hover: Color
    public let pressed: Color
    public let secondary: Color
    public let brandTop: Color
    public let brandBottom: Color
    public let iconTop: Color
    public let iconBottom: Color
}

/// 强调色是经过对比度筛选的预设，而不是任意取色器：
/// 所有 `base` 与白字的对比度均 ≥ 4.5:1，避免用户把按钮调成不可读的浅色。
public enum AccentTheme: String, CaseIterable, Identifiable {
    case inkBlue
    case forest
    case plum
    case graphite

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .inkBlue: return "墨蓝"
        case .forest: return "松绿"
        case .plum: return "紫檀"
        case .graphite: return "岩灰"
        }
    }

    public var subtitle: String {
        switch self {
        case .inkBlue: return "校样批注般的冷静"
        case .forest: return "沉静的植物学绿"
        case .plum: return "偏暖的学术紫"
        case .graphite: return "中性、克制的石墨"
        }
    }

    public var swatch: Color { palette.base }

    public var palette: AccentPalette {
        switch self {
        case .inkBlue:
            return AccentPalette(
                base: Color(red: 0.122, green: 0.373, blue: 0.541),       // #1F5F8A
                hover: Color(red: 0.165, green: 0.435, blue: 0.608),      // #2A6F9B
                pressed: Color(red: 0.090, green: 0.294, blue: 0.427),    // #174B6D
                secondary: Color(red: 0.165, green: 0.451, blue: 0.478),  // #2A737A
                brandTop: Color(red: 0.173, green: 0.463, blue: 0.627),   // #2C76A0
                brandBottom: Color(red: 0.110, green: 0.310, blue: 0.455), // #1C4F74
                iconTop: Color(red: 0.153, green: 0.392, blue: 0.514),    // #276483
                iconBottom: Color(red: 0.047, green: 0.165, blue: 0.243)  // #0C2A3E
            )
        case .forest:
            return AccentPalette(
                base: Color(red: 0.184, green: 0.420, blue: 0.310),       // #2F6B4F
                hover: Color(red: 0.227, green: 0.490, blue: 0.361),      // #3A7D5C
                pressed: Color(red: 0.141, green: 0.329, blue: 0.243),    // #24543E
                secondary: Color(red: 0.294, green: 0.451, blue: 0.373),  // #4B735F
                brandTop: Color(red: 0.247, green: 0.490, blue: 0.357),   // #3F7D5B
                brandBottom: Color(red: 0.141, green: 0.329, blue: 0.243), // #24543E
                iconTop: Color(red: 0.196, green: 0.420, blue: 0.314),    // #326B50
                iconBottom: Color(red: 0.063, green: 0.184, blue: 0.133)  // #102F22
            )
        case .plum:
            return AccentPalette(
                base: Color(red: 0.478, green: 0.247, blue: 0.353),       // #7A3F5A
                hover: Color(red: 0.549, green: 0.314, blue: 0.420),      // #8C506B
                pressed: Color(red: 0.373, green: 0.184, blue: 0.275),    // #5F2F46
                secondary: Color(red: 0.561, green: 0.333, blue: 0.392),  // #8F5564
                brandTop: Color(red: 0.541, green: 0.294, blue: 0.396),   // #8A4B65
                brandBottom: Color(red: 0.380, green: 0.184, blue: 0.275), // #612F46
                iconTop: Color(red: 0.459, green: 0.271, blue: 0.353),    // #75455A
                iconBottom: Color(red: 0.180, green: 0.082, blue: 0.133)  // #2E1522
            )
        case .graphite:
            return AccentPalette(
                base: Color(red: 0.294, green: 0.333, blue: 0.388),       // #4B5563
                hover: Color(red: 0.353, green: 0.396, blue: 0.455),      // #5A6474
                pressed: Color(red: 0.216, green: 0.255, blue: 0.318),    // #374151
                secondary: Color(red: 0.392, green: 0.455, blue: 0.545),  // #64748B
                brandTop: Color(red: 0.357, green: 0.400, blue: 0.459),   // #5B6675
                brandBottom: Color(red: 0.216, green: 0.255, blue: 0.318), // #374151
                iconTop: Color(red: 0.294, green: 0.333, blue: 0.388),    // #4B5563
                iconBottom: Color(red: 0.122, green: 0.161, blue: 0.216)  // #1F2937
            )
        }
    }
}

// MARK: - Canvas palette

public struct CanvasPalette {
    public let canvas: Color
    public let top: Color
    public let bottom: Color
    public let control: Color
    public let controlDeep: Color
    public let cardHover: Color
}

public enum CanvasTone: String, CaseIterable, Identifiable {
    case warmPaper
    case mist
    case porcelain

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .warmPaper: return "暖纸"
        case .mist: return "雾灰"
        case .porcelain: return "米白"
        }
    }

    public var subtitle: String {
        switch self {
        case .warmPaper: return "原来的暖纸色"
        case .mist: return "更冷静的灰蓝"
        case .porcelain: return "柔和的象牙白"
        }
    }

    public var palette: CanvasPalette {
        switch self {
        case .warmPaper:
            return CanvasPalette(
                canvas: Color(red: 0.953, green: 0.945, blue: 0.922),     // #F3F1EB
                top: Color(red: 0.980, green: 0.973, blue: 0.953),        // #FAF8F3
                bottom: Color(red: 0.925, green: 0.918, blue: 0.890),     // #ECEAE3
                control: Color(red: 0.898, green: 0.886, blue: 0.855),    // #E5E2DA
                controlDeep: Color(red: 0.855, green: 0.839, blue: 0.804), // #DAD6CD
                cardHover: Color(red: 0.984, green: 0.980, blue: 0.965)   // #FBFAF6
            )
        case .mist:
            return CanvasPalette(
                canvas: Color(red: 0.933, green: 0.949, blue: 0.957),     // #EEF2F4
                top: Color(red: 0.973, green: 0.980, blue: 0.984),        // #F8FAFB
                bottom: Color(red: 0.898, green: 0.922, blue: 0.933),     // #E5EBEE
                control: Color(red: 0.878, green: 0.906, blue: 0.918),    // #E0E7EA
                controlDeep: Color(red: 0.831, green: 0.867, blue: 0.882), // #D4DDE1
                cardHover: Color(red: 0.969, green: 0.980, blue: 0.984)   // #F7FAFB
            )
        case .porcelain:
            return CanvasPalette(
                canvas: Color(red: 0.961, green: 0.949, blue: 0.925),     // #F5F2EC
                top: Color(red: 0.988, green: 0.980, blue: 0.961),        // #FCFAF5
                bottom: Color(red: 0.925, green: 0.906, blue: 0.871),     // #ECE7DE
                control: Color(red: 0.902, green: 0.875, blue: 0.824),    // #E6DFD2
                controlDeep: Color(red: 0.855, green: 0.820, blue: 0.761), // #DAD1C2
                cardHover: Color(red: 0.988, green: 0.976, blue: 0.949)   // #FCF9F2
            )
        }
    }
}

// MARK: - Persisted preferences

public final class AppSettings: ObservableObject {
    public static let shared = AppSettings()

    private enum Keys {
        static let accent = "liteparse.accent"
        static let canvasTone = "liteparse.canvasTone"
        static let outputFolder = "liteparse.outputFolder"
        static let defaultPipeline = "liteparse.defaultPipeline"
        static let defaultService = "liteparse.defaultService"
    }

    private let defaults = UserDefaults.standard

    @Published public var accent: AccentTheme {
        didSet {
            defaults.set(accent.rawValue, forKey: Keys.accent)
            themeRevision &+= 1
        }
    }

    @Published public var canvasTone: CanvasTone {
        didSet {
            defaults.set(canvasTone.rawValue, forKey: Keys.canvasTone)
            themeRevision &+= 1
        }
    }

    /// 空字符串表示继续使用 backend 的默认 `outbox/`。
    @Published public var outputFolderPath: String {
        didSet { defaults.set(outputFolderPath, forKey: Keys.outputFolder) }
    }

    @Published public var defaultPipeline: PipelineMode {
        didSet { defaults.set(defaultPipeline.rawValue, forKey: Keys.defaultPipeline) }
    }

    @Published public var defaultService: TranslationService {
        didSet { defaults.set(defaultService.rawValue, forKey: Keys.defaultService) }
    }

    /// 根视图用它强制重建一次，确保静态主题令牌切换后所有子视图同步刷新。
    @Published public private(set) var themeRevision: Int = 0

    private init() {
        accent = AccentTheme(rawValue: defaults.string(forKey: Keys.accent) ?? "") ?? .inkBlue
        canvasTone = CanvasTone(rawValue: defaults.string(forKey: Keys.canvasTone) ?? "") ?? .warmPaper
        outputFolderPath = defaults.string(forKey: Keys.outputFolder) ?? ""
        defaultPipeline = .auto
        defaults.set(PipelineMode.auto.rawValue, forKey: Keys.defaultPipeline)
        defaultService = TranslationService(rawValue: defaults.string(forKey: Keys.defaultService) ?? "") ?? .bing
    }

    public var hasCustomOutputFolder: Bool {
        !outputFolderPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func resetAppearance() {
        accent = .inkBlue
        canvasTone = .warmPaper
    }

    public func resetOutputFolder() {
        outputFolderPath = ""
    }
}
