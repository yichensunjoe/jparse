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
        case .queued: return .secondary
        case .probing: return .blue
        case .processing: return .cyan
        case .completed: return .green
        case .failed: return .red
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
        case "vector": return "现代矢量学术"
        case "scanned": return "扫描专著高清"
        case "insitu": return "原位双层重构"
        default: return "智能探测中"
        }
    }

    public var docTypeColor: Color {
        switch doc_type.lowercased() {
        case "vector": return .green
        case "scanned": return .orange
        case "insitu": return .indigo
        default: return .blue
        }
    }
}

public enum PipelineMode: String, CaseIterable, Identifiable {
    case auto = "auto"
    case hdScan = "hd_scan"
    case vector = "vector_pdf2zh"
    case inSitu = "insitu_legacy"

    public var id: String { rawValue }

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
        case .auto: return "⚡️ 智能双轨"
        case .hdScan: return "💎 高清扫描"
        case .vector: return "📐 矢量排版"
        case .inSitu: return "🌐 原位双层"
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
        case .auto: return "bolt.shield.fill"
        case .hdScan: return "photo.stack.fill"
        case .vector: return "skew"
        case .inSitu: return "globe.desk.fill"
        }
    }
}

public enum TranslationService: String, CaseIterable, Identifiable {
    case bing = "bing"
    case offline = "offline"
    case google = "google"

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .bing: return "Bing 神经翻译（推荐）"
        case .offline: return "离线 CTranslate2 本地模型"
        case .google: return "Google 翻译"
        }
    }

    public var shortTitle: String {
        switch self {
        case .bing: return "🌐 Bing 云端"
        case .offline: return "💻 离线离网"
        case .google: return "🌍 Google"
        }
    }

    public var subtitle: String {
        switch self {
        case .bing: return "高保真句意表达，内建多粒度分块保护与核化工领域术语库"
        case .offline: return "100% 离线本地 INT8 神经模型，绝对保密，无网络消耗"
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

    public var indicatorColor: Color {
        switch self {
        case .disconnected: return .gray
        case .connecting: return .orange
        case .connected: return .green
        case .error: return .red
        }
    }
}
