//
//  Generado por html2ios. Podés editar este archivo libremente.
//

import SwiftUI
import WebKit
import SafariServices
import GoogleMobileAds
import AppTrackingTransparency

// MARK: - Configuración

enum Cfg {
    /// Vacío = cargar los archivos empaquetados. Con valor = cargar esa dirección.
    static let remoteURL     = ""
    static let indexFile     = "index.html"
    static let allowBounce   = false
    static let pullToRefresh = false
    static let externalMode  = "inapp"   // safari | inapp | same
    static let bgColor       = UIColor(red: 0.067, green: 0.067, blue: 0.067, alpha: 1)
    static let interstitialUnitID = "ca-app-pub-5906038972202011/3088412895"
    static let interstitialEvery  = 1
    static let interstitialAfter: TimeInterval = 40
    static let interstitialOnce   = false
    static let interstitialGap: TimeInterval = 60

    static var isRemote: Bool { !remoteURL.isEmpty }

    static var localRoot: URL? {
        Bundle.main.url(forResource: "www", withExtension: nil)
    }
    static var localIndex: URL? {
        localRoot?.appendingPathComponent(indexFile)
    }
}

// MARK: - Punto de entrada

@main
struct GeneratedApp: App {
    init() { startAds() }

    var body: some Scene {
        WindowGroup {
            RootView()
                .ignoresSafeArea(.keyboard)
                .statusBarHidden(false)
        }
    }
}

// MARK: - Vista raíz

struct RootView: View {
    @StateObject private var model = WebModel()

    var body: some View {
        ZStack {
            Color(Cfg.bgColor).ignoresSafeArea()

            WebContainer(model: model)
                .opacity(model.ready ? 1 : 0)
                .animation(.easeOut(duration: 0.25), value: model.ready)

            if !model.ready && model.error == nil {
                SplashView()
            }
            if let message = model.error {
                ErrorView(message: message) { model.reload() }
            }
        }
    }
}

// MARK: - Anuncios

/// Gestiona el anuncio a pantalla completa.
///
/// La página web sólo avisa de que ha llegado un buen momento; la decisión de
/// mostrarlo o no se toma aquí. Enseñarlo en cada partida incumpliría las
/// políticas de AdMob sobre interrupciones excesivas, así que hay dos frenos:
/// una cuenta de avisos y un tiempo mínimo entre anuncios.
final class AdCoordinator: NSObject, FullScreenContentDelegate {
    static let shared = AdCoordinator()

    private var anuncio: InterstitialAd?
    private var avisos = 0
    private var ultimo = Date.distantPast
    private let arranque = Date()
    private var yaMostrado = false

    func precargar() {
        guard !Cfg.interstitialUnitID.isEmpty else { return }
        Task { @MainActor in
            do {
                let ad = try await InterstitialAd.load(
                    with: Cfg.interstitialUnitID, request: Request())
                ad.fullScreenContentDelegate = self
                anuncio = ad
            } catch {
                anuncio = nil
            }
        }
    }

    /// Llamado desde la web con Native.interstitial()
    func momentoOportuno() {
        guard !Cfg.interstitialUnitID.isEmpty else { return }

        // Una sola vez por sesión, si así se configuró
        if Cfg.interstitialOnce && yaMostrado { return }

        // Nada antes de que pase el tiempo mínimo desde que se abrió la app
        guard Date().timeIntervalSince(arranque) >= Cfg.interstitialAfter else { return }

        avisos += 1
        guard avisos % Cfg.interstitialEvery == 0,
              Date().timeIntervalSince(ultimo) > Cfg.interstitialGap else { return }

        guard let ad = anuncio,
              let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let root = scene.keyWindow?.rootViewController else {
            precargar()          // no había ninguno listo: dejamos uno preparado
            return
        }
        ultimo = Date()
        yaMostrado = true
        anuncio = nil
        ad.present(from: root)
    }

    func adDidDismissFullScreenContent(_ ad: FullScreenPresentingAd) {
        guard !Cfg.interstitialOnce else { return }   // no habrá otro esta sesión
        precargar()
    }

    func ad(_ ad: FullScreenPresentingAd,
            didFailToPresentFullScreenContentWithError error: Error) {
        anuncio = nil
        precargar()
    }
}

/// Pide permiso de seguimiento y sólo después arranca el SDK. Sin permiso los
/// anuncios se siguen mostrando, pero sin personalizar.
func startAds() {
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
        ATTrackingManager.requestTrackingAuthorization { _ in
            MobileAds.shared.start { _ in
                AdCoordinator.shared.precargar()
            }
        }
    }
}


struct SplashView: View {
    var body: some View {
        ZStack {
            Color(Cfg.bgColor).ignoresSafeArea()
            VStack(spacing: 18) {
                if let icon = UIImage(named: "AppIcon") {
                    Image(uiImage: icon)
                        .resizable().frame(width: 84, height: 84)
                        .clipShape(RoundedRectangle(cornerRadius: 19, style: .continuous))
                }
                ProgressView().tint(.white.opacity(0.85))
            }
        }
    }
}

struct ErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ZStack {
            Color(Cfg.bgColor).ignoresSafeArea()
            VStack(spacing: 16) {
                Image(systemName: "wifi.exclamationmark")
                    .font(.system(size: 42, weight: .light))
                    .foregroundStyle(.white.opacity(0.85))
                Text("No se pudo cargar")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white)
                Text(message)
                    .font(.footnote)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.white.opacity(0.65))
                    .padding(.horizontal, 34)
                Button(action: retry) {
                    Text("Reintentar")
                        .font(.body.weight(.semibold))
                        .padding(.horizontal, 26).padding(.vertical, 12)
                        .background(.white.opacity(0.16), in: Capsule())
                        .foregroundStyle(.white)
                }
                .padding(.top, 4)
            }
        }
    }
}

// MARK: - Modelo

final class WebModel: ObservableObject {
    @Published var ready = false
    @Published var error: String?
    weak var webView: WKWebView?

    func reload() {
        error = nil
        guard let webView else { return }
        if Cfg.isRemote, let url = URL(string: Cfg.remoteURL) {
            webView.load(URLRequest(url: url))
        } else if let index = Cfg.localIndex, let root = Cfg.localRoot {
            webView.loadFileURL(index, allowingReadAccessTo: root)
        }
    }
}

// MARK: - WebView

struct WebContainer: UIViewRepresentable {
    @ObservedObject var model: WebModel

    func makeCoordinator() -> Coordinator { Coordinator(model: model) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        config.defaultWebpagePreferences.allowsContentJavaScript = true

        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "native")
        controller.addUserScript(WKUserScript(source: Self.bridgeJS,
                                              injectionTime: .atDocumentStart,
                                              forMainFrameOnly: false))
        config.userContentController = controller

        let web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = context.coordinator
        web.uiDelegate = context.coordinator
        web.allowsBackForwardNavigationGestures = Cfg.isRemote
        web.scrollView.bounces = Cfg.allowBounce
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.isOpaque = false
        web.backgroundColor = Cfg.bgColor
        web.scrollView.backgroundColor = Cfg.bgColor

        if Cfg.pullToRefresh {
            let refresh = UIRefreshControl()
            refresh.addTarget(context.coordinator,
                              action: #selector(Coordinator.pulled(_:)),
                              for: .valueChanged)
            web.scrollView.refreshControl = refresh
        }

        model.webView = web
        model.reload()
        return web
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    /// Puente disponible en la página como window.Native
    static let bridgeJS = """
    (function () {
      function post(payload) {
        try { window.webkit.messageHandlers.native.postMessage(payload); } catch (e) {}
      }
      window.Native = {
        isApp: true,
        platform: 'ios',
        haptic: function (style) { post({ action: 'haptic', style: style || 'light' }); },
        share:  function (o) { o = o || {}; post({ action: 'share', text: o.text || '', url: o.url || '' }); },
        interstitial: function () { post({ action: 'interstitial' }); },
        open:   function (url) { post({ action: 'open', url: url }); }
      };
      document.documentElement.classList.add('native-ios');
      var s = document.createElement('style');
      s.textContent = '.native-ios{-webkit-tap-highlight-color:transparent}';
      document.documentElement.appendChild(s);
    })();
    """

    // MARK: Coordinator

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        let model: WebModel
        init(model: WebModel) { self.model = model }

        @objc func pulled(_ sender: UIRefreshControl) {
            model.webView?.reload()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { sender.endRefreshing() }
        }

        private func isInternal(_ url: URL) -> Bool {
            if url.isFileURL { return true }
            guard Cfg.isRemote,
                  let start = URL(string: Cfg.remoteURL),
                  let host = url.host, let startHost = start.host else { return false }
            return host == startHost
        }

        private func openOutside(_ url: URL) {
            switch Cfg.externalMode {
            case "same":
                model.webView?.load(URLRequest(url: url))
            case "safari":
                UIApplication.shared.open(url)
            default:
                guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                      let root = scene.keyWindow?.rootViewController else {
                    UIApplication.shared.open(url); return
                }
                let safari = SFSafariViewController(url: url)
                safari.preferredControlTintColor = .white
                root.present(safari, animated: true)
            }
        }

        func webView(_ webView: WKWebView,
                     decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel); return
            }
            switch url.scheme?.lowercased() {
            case "http", "https":
                if isInternal(url) {
                    decisionHandler(.allow)
                } else {
                    decisionHandler(.cancel)
                    openOutside(url)
                }
            case "file", "about", "data", "blob":
                decisionHandler(.allow)
            case "mailto", "tel", "sms", "facetime", "maps", "itms-apps":
                decisionHandler(.cancel)
                UIApplication.shared.open(url)
            default:
                decisionHandler(.cancel)
            }
        }

        /// Enlaces con target="_blank": se abren en la misma vista.
        func webView(_ webView: WKWebView,
                     createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = navigationAction.request.url {
                if isInternal(url) { webView.load(URLRequest(url: url)) } else { openOutside(url) }
            }
            return nil
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            model.ready = true
            model.error = nil
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            report(error)
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            report(error)
        }

        private func report(_ error: Error) {
            let ns = error as NSError
            if ns.code == NSURLErrorCancelled { return }
            model.error = ns.localizedDescription
            model.ready = true
        }

        /// Diálogos JavaScript nativos
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            present(alert: message, confirm: false) { _ in completionHandler() }
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            present(alert: message, confirm: true) { ok in completionHandler(ok) }
        }

        private func present(alert message: String, confirm: Bool, done: @escaping (Bool) -> Void) {
            guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                  let root = scene.keyWindow?.rootViewController else { done(false); return }
            let ac = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            if confirm {
                ac.addAction(UIAlertAction(title: "Cancelar", style: .cancel) { _ in done(false) })
            }
            ac.addAction(UIAlertAction(title: "Aceptar", style: .default) { _ in done(true) })
            root.present(ac, animated: true)
        }

        // Puente desde JavaScript
        func userContentController(_ controller: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard let body = message.body as? [String: Any],
                  let action = body["action"] as? String else { return }

            switch action {
            case "haptic":
                let style = body["style"] as? String ?? "light"
                switch style {
                case "success": UINotificationFeedbackGenerator().notificationOccurred(.success)
                case "warning": UINotificationFeedbackGenerator().notificationOccurred(.warning)
                case "error":   UINotificationFeedbackGenerator().notificationOccurred(.error)
                case "medium":  UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                case "heavy":   UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
                default:        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                }

            case "share":
                var items: [Any] = []
                if let text = body["text"] as? String, !text.isEmpty { items.append(text) }
                if let link = body["url"] as? String, let url = URL(string: link) { items.append(url) }
                guard !items.isEmpty,
                      let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                      let root = scene.keyWindow?.rootViewController else { return }
                let sheet = UIActivityViewController(activityItems: items, applicationActivities: nil)
                sheet.popoverPresentationController?.sourceView = root.view
                sheet.popoverPresentationController?.sourceRect =
                    CGRect(x: root.view.bounds.midX, y: root.view.bounds.maxY, width: 0, height: 0)
                root.present(sheet, animated: true)

            case "interstitial":
                AdCoordinator.shared.momentoOportuno()

            case "open":
                if let link = body["url"] as? String, let url = URL(string: link) {
                    openOutside(url)
                }

            default:
                break
            }
        }
    }
}
