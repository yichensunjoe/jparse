import Foundation
import SwiftUI

public enum TaskStatus: String, Codable {
    case queued = "queued"
    case probing = "probing"
    case processing = "processing"
    case completed = "completed"
    case failed = "failed"

    public var localizedDescription: String {
        switch self {
        case .queued: return "等待排队"
        case .probing: return "探测版面中"
        case .processing: return "正在重构与翻译"
        case .completed: return "转换完成"
        case .failed: return "处理失败"
        }
    }

    public var tintColor: Color {
        switch self {
        case .queued: return LightTheme.textMuted
        case .probing: return LightTheme.statusProbing
        case .processing: return LightTheme.statusProcessing
        case .completed: return LightTheme.accentGreen
        case .failed: return LightTheme.accentRed
        }
    }

    public var iconName: String {
        switch self {
        case .queued: return "clock"
        case .probing: return "sparkles.magnifyingglass"
        case .processing: return "gearshape.arrow.triangle.2.circlepath"
        case .completed: return "checkmark.seal.fill"
        case .failed: return "exclamationmark.triangle.fill"
        }
    }
}

public struct OutputFileItem: Codable, Identifiable, Hashable {
    public var id: String { path }
    public let name: String
    public let path: String
    public let size: Int
    public let is_pdf: Bool
    public let is_html: Bool

    public var formattedSize: String {
        if size <= 0 { return "" }
        if size < 1024 { return "\(size) B" }
        if size < 1024 * 1024 { return String(format: "%.1f KB", Double(size) / 1024.0) }
        return String(format: "%.1f MB", Double(size) / (1024.0 * 1024.0))
    }
}

public struct TaskItem: Codable, Identifiable, Hashable {
    public let id: String
    public let filename: String
    public let relative_path: String
    public let file_size: Int
    public let input_path: String
    public var status: TaskStatus
    public var doc_type: String
    public var progress: Double
    public var output_files: [OutputFileItem]
    public var error: String?
    public var created_at: String
    public var duration: Double

    public var formattedSize: String {
        if file_size <= 0 { return "0 B" }
        if file_size < 1024 { return "\(file_size) B" }
        if file_size < 1024 * 1024 { return String(format: "%.1f KB", Double(file_size) / 1024.0) }
        return String(format: "%.1f MB", Double(file_size) / (1024.0 * 1024.0))
    }

    public var docTypeBadgeText: String {
        switch doc_type.lowercased() {
        case "vector": return "矢量学术"
        case "scanned": return "扫描专著"
        case "insitu": return "原位双层"
        default: return "智能探测中"
        }
    }

    public var docTypeColor: Color {
        switch doc_type.lowercased() {
        case "vector": return LightTheme.accentGreen
        case "scanned": return LightTheme.accentAmber
        case "insitu": return LightTheme.accentIndigo
        default: return LightTheme.accentBlue
        }
    }
}

public enum PipelineMode: String, CaseIterable, Identifiable {
    case auto = "auto"
    case hdScan = "hd_scan"
    case vector = "vector_pdf2zh"
    case inSitu = "insitu_legacy"

    public var id: String { rawValue }

    /// 保留已保存的 rawValue，同时向路由器发送它实际支持的模式名。
    public var requestValue: String {
        switch self {
        case .auto: return "auto"
        case .hdScan: return "scanned"
        case .vector: return "vector"
        case .inSitu: return "insitu_legacy"
        }
    }

    public var title: String {
        switch self {
        case .auto: return "智能双轨自动路由"
        case .hdScan: return "扫描件高清出版重构"
        case .vector: return "现代矢量学术排版"
        case .inSitu: return "历史原位双层 HTML"
        }
    }

    public var shortTitle: String {
        switch self {
        case .auto: return "智能双轨"
        case .hdScan: return "高清扫描"
        case .vector: return "矢量排版"
        case .inSitu: return "原位双层"
        }
    }

    public var subtitle: String {
        switch self {
        case .auto: return "自动判定：数字论文走 pdf2zh 矢量擦除，扫描件走 OpenDataLoader 高清重构"
        case .hdScan: return "180-200 DPI 超清原图裁剪 + 宋体出版字号 + 三线表 + 1:1 双语交替对照"
        case .vector: return "公式保护、零失真字体擦除替换、学术双栏出版级矢量排版"
        case .inSitu: return "保留历史双层 HTML 网页交互，适合打字机原始字迹核对"
        }
    }

    public var iconName: String {
        switch self {
        case .auto: return "bolt.fill"
        case .hdScan: return "photo.stack.fill"
        case .vector: return "text.alignleft"
        case .inSitu: return "globe"
        }
    }
}

public enum TranslationService: String, CaseIterable, Identifiable {
    case bing = "bing"
    case google = "google"

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .bing: return "Bing 神经翻译（推荐）"
        case .google: return "Google 翻译"
        }
    }

    public var shortTitle: String {
        switch self {
        case .bing: return "Bing"
        case .google: return "Google"
        }
    }

    public var subtitle: String {
        switch self {
        case .bing: return "高保真句意表达，内建多粒度分块保护与核化工领域术语库"
        case .google: return "备选通用多语言引擎"
        }
    }
}

public enum BackendConnectionStatus: Equatable {
    case disconnected
    case connecting
    case connected(port: Int)
    case error(String)

    public var isConnected: Bool {
        if case .connected = self { return true }
        return false
    }

    public var statusText: String {
        switch self {
        case .disconnected: return "本地引擎未连接"
        case .connecting: return "正在连接本地智能引擎..."
        case .connected(let port): return "本地智能引擎已就绪 · 端口 \(port)"
        case .error(let msg): return "服务异常: \(msg)"
        }
    }

    /// 顶栏胶囊用的短文案：状态必须真实，不能永远显示“就绪”。
    public var shortLabel: String {
        switch self {
        case .disconnected: return "本地引擎未连接"
        case .connecting: return "正在启动引擎"
        case .connected: return "本地引擎就绪"
        case .error: return "引擎异常"
        }
    }

    /// 窄窗口下的极简文案。
    public var compactLabel: String {
        switch self {
        case .disconnected: return "未连接"
        case .connecting: return "启动中"
        case .connected: return "就绪"
        case .error: return "异常"
        }
    }

    public var indicatorColor: Color {
        switch self {
        case .disconnected: return LightTheme.textMuted
        case .connecting: return LightTheme.accentAmber
        case .connected: return LightTheme.accentGreen
        case .error: return LightTheme.accentRed
        }
    }
}
