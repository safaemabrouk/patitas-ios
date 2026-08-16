#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
html2ios — convierte una página HTML en un proyecto de Xcode listo para la App Store.

Genera una app nativa que muestra tu HTML en un WKWebView, con los archivos
empaquetados dentro (funciona sin conexión), más el flujo de GitHub Actions
para compilarla y subirla a App Store Connect sin necesidad de un Mac.

Uso mínimo:
    python3 html2ios.py --input mi-pagina.html --name "Mi App" --bundle-id com.midominio.miapp

Requisitos: Python 3.8 o superior. Pillow es opcional (sólo para generar el icono).
Licencia: uso libre.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import zlib
import sys
import unicodedata
from pathlib import Path

VERSION = "1.2"

# ────────────────────────────────────────────────────────────────────────────
#  utilidades
# ────────────────────────────────────────────────────────────────────────────

def die(msg):
    print(f"\n  ERROR: {msg}\n", file=sys.stderr)
    sys.exit(1)


def info(msg):
    print(f"  {msg}")


def slug(text):
    """Nombre seguro para carpetas y targets de Xcode."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "", text)
    return text or "App"


def uid(*parts):
    """Identificador de 24 hex, estable para la misma entrada."""
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()
    return h[:24].upper()


def hex_to_rgb(value):
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6 or any(c not in "0123456789abcdefABCDEF" for c in v):
        die(f"color inválido: {value} (se esperaba algo como #12153F)")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def png_size(path):
    """Dimensiones de un PNG leyendo la cabecera, sin depender de Pillow."""
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def write(path, content, mode=None):
    """Escribe siempre con saltos de línea Unix.

    En Windows, Python traduciría \\n a \\r\\n. El flujo de GitHub Actions se
    ejecuta en macOS con bash, y bash falla con «$'\\r': command not found» si
    el YAML llega con saltos de Windows. Este newline="\\n" es lo que evita que
    el proyecto generado desde un PC no compile.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    if mode:
        os.chmod(path, mode)


# ────────────────────────────────────────────────────────────────────────────
#  código Swift de la app
# ────────────────────────────────────────────────────────────────────────────

SWIFT_APP = r'''//
//  Generado por html2ios. Podés editar este archivo libremente.
//

import SwiftUI
import WebKit
import SafariServices
@@ADS_IMPORTS@@

// MARK: - Configuración

enum Cfg {
    /// Vacío = cargar los archivos empaquetados. Con valor = cargar esa dirección.
    static let remoteURL     = "@@REMOTE_URL@@"
    static let indexFile     = "@@INDEX@@"
    static let allowBounce   = @@BOUNCE@@
    static let pullToRefresh = @@PULL@@
    static let externalMode  = "@@EXTERNAL@@"   // safari | inapp | same
    static let bgColor       = UIColor(red: @@BG_R@@, green: @@BG_G@@, blue: @@BG_B@@, alpha: 1)
    static let bannerUnitID  = "@@ADS_BANNER_ID@@"
    static let interstitialUnitID = "@@ADS_INTER_ID@@"
    static let interstitialEvery  = @@ADS_INTER_EVERY@@
    static let interstitialAfter: TimeInterval = @@ADS_INTER_AFTER@@
    static let interstitialOnce   = @@ADS_INTER_ONCE@@
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
        VStack(spacing: 0) {
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
            AdBanner()
        }
    }
}

// MARK: - Anuncios

@@ADS_CODE@@

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
'''

# ────────────────────────────────────────────────────────────────────────────
#  project.pbxproj
# ────────────────────────────────────────────────────────────────────────────

PBXPROJ = r'''// !$*UTF8*$!
{
	archiveVersion = 1;
	classes = {
	};
	objectVersion = 56;
	objects = {

/* Begin PBXBuildFile section */
		@@BF_SWIFT@@ /* AppMain.swift in Sources */ = {isa = PBXBuildFile; fileRef = @@FR_SWIFT@@ /* AppMain.swift */; };
		@@BF_ASSETS@@ /* Assets.xcassets in Resources */ = {isa = PBXBuildFile; fileRef = @@FR_ASSETS@@ /* Assets.xcassets */; };
		@@BF_WWW@@ /* www in Resources */ = {isa = PBXBuildFile; fileRef = @@FR_WWW@@ /* www */; };
@@ADS_BUILDFILE@@/* End PBXBuildFile section */

/* Begin PBXFileReference section */
		@@FR_APP@@ /* @@NAME@@.app */ = {isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = "@@NAME@@.app"; sourceTree = BUILT_PRODUCTS_DIR; };
		@@FR_SWIFT@@ /* AppMain.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = AppMain.swift; sourceTree = "<group>"; };
		@@FR_ASSETS@@ /* Assets.xcassets */ = {isa = PBXFileReference; lastKnownFileType = folder.assetcatalog; path = Assets.xcassets; sourceTree = "<group>"; };
		@@FR_INFO@@ /* Info.plist */ = {isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; };
		@@FR_WWW@@ /* www */ = {isa = PBXFileReference; lastKnownFileType = folder; path = www; sourceTree = "<group>"; };
/* End PBXFileReference section */

/* Begin PBXFrameworksBuildPhase section */
		@@FRAMEWORKS@@ /* Frameworks */ = {
			isa = PBXFrameworksBuildPhase;
			buildActionMask = 2147483647;
			files = (
@@ADS_FRAMEWORK@@			);
			runOnlyForDeploymentPostprocessing = 0;
		};
/* End PBXFrameworksBuildPhase section */

/* Begin PBXGroup section */
		@@GROUP_ROOT@@ = {
			isa = PBXGroup;
			children = (
				@@GROUP_APP@@ /* @@NAME@@ */,
				@@GROUP_PRODUCTS@@ /* Products */,
			);
			sourceTree = "<group>";
		};
		@@GROUP_APP@@ /* @@NAME@@ */ = {
			isa = PBXGroup;
			children = (
				@@FR_SWIFT@@ /* AppMain.swift */,
				@@FR_ASSETS@@ /* Assets.xcassets */,
				@@FR_WWW@@ /* www */,
				@@FR_INFO@@ /* Info.plist */,
			);
			path = "@@NAME@@";
			sourceTree = "<group>";
		};
		@@GROUP_PRODUCTS@@ /* Products */ = {
			isa = PBXGroup;
			children = (
				@@FR_APP@@ /* @@NAME@@.app */,
			);
			name = Products;
			sourceTree = "<group>";
		};
/* End PBXGroup section */

/* Begin PBXNativeTarget section */
		@@TARGET@@ /* @@NAME@@ */ = {
			isa = PBXNativeTarget;
			buildConfigurationList = @@CONFLIST_TARGET@@ /* Build configuration list for PBXNativeTarget "@@NAME@@" */;
			buildPhases = (
				@@SOURCES@@ /* Sources */,
				@@FRAMEWORKS@@ /* Frameworks */,
				@@RESOURCES@@ /* Resources */,
			);
			buildRules = (
			);
			dependencies = (
			);
			name = "@@NAME@@";
@@ADS_PKG_PRODS@@			productName = "@@NAME@@";
			productReference = @@FR_APP@@ /* @@NAME@@.app */;
			productType = "com.apple.product-type.application";
		};
/* End PBXNativeTarget section */

/* Begin PBXProject section */
		@@PROJECT@@ /* Project object */ = {
			isa = PBXProject;
			attributes = {
				BuildIndependentTargetsInParallel = 1;
				LastSwiftUpdateCheck = 2600;
				LastUpgradeCheck = 2600;
				TargetAttributes = {
					@@TARGET@@ = {
						CreatedOnToolsVersion = 26.0;
					};
				};
			};
			buildConfigurationList = @@CONFLIST_PROJECT@@ /* Build configuration list for PBXProject "@@NAME@@" */;
			compatibilityVersion = "Xcode 14.0";
			developmentRegion = en;
			hasScannedForEncodings = 0;
			knownRegions = (
				en,
				Base,
			);
			mainGroup = @@GROUP_ROOT@@;
@@ADS_PKG_REFS@@			productRefGroup = @@GROUP_PRODUCTS@@ /* Products */;
			projectDirPath = "";
			projectRoot = "";
			targets = (
				@@TARGET@@ /* @@NAME@@ */,
			);
		};
/* End PBXProject section */

/* Begin PBXResourcesBuildPhase section */
		@@RESOURCES@@ /* Resources */ = {
			isa = PBXResourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				@@BF_WWW@@ /* www in Resources */,
				@@BF_ASSETS@@ /* Assets.xcassets in Resources */,
			);
			runOnlyForDeploymentPostprocessing = 0;
		};
/* End PBXResourcesBuildPhase section */

/* Begin PBXSourcesBuildPhase section */
		@@SOURCES@@ /* Sources */ = {
			isa = PBXSourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				@@BF_SWIFT@@ /* AppMain.swift in Sources */,
			);
			runOnlyForDeploymentPostprocessing = 0;
		};
/* End PBXSourcesBuildPhase section */

/* Begin XCBuildConfiguration section */
		@@CONF_PROJ_DEBUG@@ /* Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ALWAYS_SEARCH_USER_PATHS = NO;
				CLANG_ENABLE_MODULES = YES;
				CLANG_ENABLE_OBJC_ARC = YES;
				COPY_PHASE_STRIP = NO;
				DEBUG_INFORMATION_FORMAT = dwarf;
				ENABLE_STRICT_OBJC_MSGSEND = YES;
				ENABLE_TESTABILITY = YES;
				GCC_C_LANGUAGE_STANDARD = gnu17;
				GCC_DYNAMIC_NO_PIC = NO;
				GCC_NO_COMMON_BLOCKS = YES;
				GCC_OPTIMIZATION_LEVEL = 0;
				GCC_PREPROCESSOR_DEFINITIONS = (
					"DEBUG=1",
					"$(inherited)",
				);
				IPHONEOS_DEPLOYMENT_TARGET = @@MIN_IOS@@;
				MTL_ENABLE_DEBUG_INFO = INCLUDE_SOURCE;
				MTL_FAST_MATH = YES;
				ONLY_ACTIVE_ARCH = YES;
				SDKROOT = iphoneos;
				SWIFT_ACTIVE_COMPILATION_CONDITIONS = "DEBUG $(inherited)";
				SWIFT_OPTIMIZATION_LEVEL = "-Onone";
			};
			name = Debug;
		};
		@@CONF_PROJ_RELEASE@@ /* Release */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ALWAYS_SEARCH_USER_PATHS = NO;
				CLANG_ENABLE_MODULES = YES;
				CLANG_ENABLE_OBJC_ARC = YES;
				COPY_PHASE_STRIP = NO;
				DEBUG_INFORMATION_FORMAT = "dwarf-with-dsym";
				ENABLE_NS_ASSERTIONS = NO;
				ENABLE_STRICT_OBJC_MSGSEND = YES;
				GCC_C_LANGUAGE_STANDARD = gnu17;
				GCC_NO_COMMON_BLOCKS = YES;
				IPHONEOS_DEPLOYMENT_TARGET = @@MIN_IOS@@;
				MTL_ENABLE_DEBUG_INFO = NO;
				MTL_FAST_MATH = YES;
				SDKROOT = iphoneos;
				SWIFT_COMPILATION_MODE = wholemodule;
				VALIDATE_PRODUCT = YES;
			};
			name = Release;
		};
		@@CONF_TARGET_DEBUG@@ /* Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
				ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME = AccentColor;
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = @@BUILD@@;
				@@DEV_TEAM@@ENABLE_USER_SCRIPT_SANDBOXING = YES;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = "@@NAME@@/Info.plist";
				IPHONEOS_DEPLOYMENT_TARGET = @@MIN_IOS@@;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = @@VERSION@@;
				PRODUCT_BUNDLE_IDENTIFIER = "@@BUNDLE_ID@@";
				PRODUCT_NAME = "$(TARGET_NAME)";
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "@@DEVICES@@";
			};
			name = Debug;
		};
		@@CONF_TARGET_RELEASE@@ /* Release */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
				ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME = AccentColor;
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = @@BUILD@@;
				@@DEV_TEAM@@ENABLE_USER_SCRIPT_SANDBOXING = YES;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = "@@NAME@@/Info.plist";
				IPHONEOS_DEPLOYMENT_TARGET = @@MIN_IOS@@;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
				);
				MARKETING_VERSION = @@VERSION@@;
				PRODUCT_BUNDLE_IDENTIFIER = "@@BUNDLE_ID@@";
				PRODUCT_NAME = "$(TARGET_NAME)";
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "@@DEVICES@@";
			};
			name = Release;
		};
/* End XCBuildConfiguration section */

/* Begin XCConfigurationList section */
		@@CONFLIST_PROJECT@@ /* Build configuration list for PBXProject "@@NAME@@" */ = {
			isa = XCConfigurationList;
			buildConfigurations = (
				@@CONF_PROJ_DEBUG@@ /* Debug */,
				@@CONF_PROJ_RELEASE@@ /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		};
		@@CONFLIST_TARGET@@ /* Build configuration list for PBXNativeTarget "@@NAME@@" */ = {
			isa = XCConfigurationList;
			buildConfigurations = (
				@@CONF_TARGET_DEBUG@@ /* Debug */,
				@@CONF_TARGET_RELEASE@@ /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		};
/* End XCConfigurationList section */
@@ADS_SECTIONS@@	};
	rootObject = @@PROJECT@@ /* Project object */;
}
'''

XCSCHEME = r'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2600" version="1.7">
   <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES">
      <BuildActionEntries>
         <BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">
            <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="@@TARGET@@" BuildableName="@@NAME@@.app" BlueprintName="@@NAME@@" ReferencedContainer="container:@@NAME@@.xcodeproj"/>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.DebuggerFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"/>
   <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.DebuggerFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES">
      <BuildableProductRunnable runnableDebuggingMode="0">
         <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="@@TARGET@@" BuildableName="@@NAME@@.app" BlueprintName="@@NAME@@" ReferencedContainer="container:@@NAME@@.xcodeproj"/>
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES">
      <BuildableProductRunnable runnableDebuggingMode="0">
         <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="@@TARGET@@" BuildableName="@@NAME@@.app" BlueprintName="@@NAME@@" ReferencedContainer="container:@@NAME@@.xcodeproj"/>
      </BuildableProductRunnable>
   </ProfileAction>
   <AnalyzeAction buildConfiguration="Debug"/>
   <ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>
'''

WORKSPACE = '''<?xml version="1.0" encoding="UTF-8"?>
<Workspace version="1.0">
   <FileRef location="self:"></FileRef>
</Workspace>
'''

# ────────────────────────────────────────────────────────────────────────────
#  flujo de GitHub Actions
# ────────────────────────────────────────────────────────────────────────────

WORKFLOW = r'''name: Compilar y subir a App Store Connect

# Se lanza a mano desde la pestaña Actions, o al publicar una etiqueta v1.0, v1.1...
on:
  workflow_dispatch:
    inputs:
      subir:
        description: "Subir a App Store Connect (si no, sólo compila)"
        type: boolean
        default: true
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: macos-26          # imagen con Xcode 26, obligatorio desde abril de 2026
    timeout-minutes: 45

    env:
      PROYECTO: "@@NAME@@.xcodeproj"
      ESQUEMA: "@@NAME@@"
      BUNDLE_ID: "@@BUNDLE_ID@@"

    steps:
      - name: Descargar el repositorio
        uses: actions/checkout@v4

      - name: Comprobar la versión de Xcode
        run: |
          xcodebuild -version
          MAJOR=$(xcodebuild -version | head -1 | sed -E 's/Xcode ([0-9]+).*/\1/')
          if [ "$MAJOR" -lt 26 ]; then
            echo "::error::Se necesita Xcode 26 o superior. Encontrado: $MAJOR"
            exit 1
          fi

      - name: Preparar la clave de App Store Connect
        env:
          KEY_ID: ${{ secrets.APPSTORE_KEY_ID }}
          PRIVATE_KEY: ${{ secrets.APPSTORE_PRIVATE_KEY }}
        run: |
          if [ -z "$KEY_ID" ] || [ -z "$PRIVATE_KEY" ]; then
            echo "::error::Faltan los secretos APPSTORE_KEY_ID o APPSTORE_PRIVATE_KEY"
            exit 1
          fi
          mkdir -p ~/private_keys ~/.appstoreconnect/private_keys
          echo "$PRIVATE_KEY" > ~/private_keys/AuthKey_${KEY_ID}.p8
          cp ~/private_keys/AuthKey_${KEY_ID}.p8 ~/.appstoreconnect/private_keys/
          chmod 600 ~/private_keys/AuthKey_${KEY_ID}.p8
          echo "KEY_PATH=$HOME/private_keys/AuthKey_${KEY_ID}.p8" >> $GITHUB_ENV

      - name: Numerar la compilación
        run: |
          # Cada ejecución sube el número de build; App Store Connect no acepta repetidos.
          BUILD=$(( ${{ github.run_number }} + @@BUILD@@ ))
          echo "Número de compilación: $BUILD"
          /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD" "@@NAME@@/Info.plist"
          echo "BUILD_NUMBER=$BUILD" >> $GITHUB_ENV

      - name: Archivar
        env:
          KEY_ID: ${{ secrets.APPSTORE_KEY_ID }}
          ISSUER_ID: ${{ secrets.APPSTORE_ISSUER_ID }}
          TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
        run: |
          # pipefail es imprescindible: sin él, un fallo de xcodebuild quedaría
          # tapado por el código de salida de xcbeautify y el flujo daría verde.
          set -o pipefail
          bonito() {
            if command -v xcbeautify >/dev/null 2>&1; then
              "$@" | xcbeautify --renderer github-actions
            else
              "$@"
            fi
          }
          bonito xcodebuild archive \
            -project "$PROYECTO" \
            -scheme "$ESQUEMA" \
            -configuration Release \
            -destination "generic/platform=iOS" \
            -archivePath "$RUNNER_TEMP/app.xcarchive" \
            -allowProvisioningUpdates \
            -authenticationKeyPath "$KEY_PATH" \
            -authenticationKeyID "$KEY_ID" \
            -authenticationKeyIssuerID "$ISSUER_ID" \
            DEVELOPMENT_TEAM="$TEAM_ID" \
            CODE_SIGN_STYLE=Automatic

      - name: Exportar el .ipa
        env:
          KEY_ID: ${{ secrets.APPSTORE_KEY_ID }}
          ISSUER_ID: ${{ secrets.APPSTORE_ISSUER_ID }}
          TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
        run: |
          sed "s/__TEAM_ID__/$TEAM_ID/" ExportOptions.plist > "$RUNNER_TEMP/ExportOptions.plist"
          xcodebuild -exportArchive \
            -archivePath "$RUNNER_TEMP/app.xcarchive" \
            -exportPath "$RUNNER_TEMP/ipa" \
            -exportOptionsPlist "$RUNNER_TEMP/ExportOptions.plist" \
            -allowProvisioningUpdates \
            -authenticationKeyPath "$KEY_PATH" \
            -authenticationKeyID "$KEY_ID" \
            -authenticationKeyIssuerID "$ISSUER_ID"
          ls -lh "$RUNNER_TEMP/ipa"

      - name: Guardar el .ipa como artefacto
        uses: actions/upload-artifact@v4
        with:
          name: ipa-build-${{ env.BUILD_NUMBER }}
          path: ${{ runner.temp }}/ipa/*.ipa
          retention-days: 30

      - name: Validar antes de subir
        if: inputs.subir || startsWith(github.ref, 'refs/tags/')
        env:
          KEY_ID: ${{ secrets.APPSTORE_KEY_ID }}
          ISSUER_ID: ${{ secrets.APPSTORE_ISSUER_ID }}
        run: |
          IPA=$(ls "$RUNNER_TEMP"/ipa/*.ipa | head -1)
          xcrun altool --validate-app -f "$IPA" -t ios \
            --apiKey "$KEY_ID" --apiIssuer "$ISSUER_ID"

      - name: Subir a App Store Connect
        if: inputs.subir || startsWith(github.ref, 'refs/tags/')
        env:
          KEY_ID: ${{ secrets.APPSTORE_KEY_ID }}
          ISSUER_ID: ${{ secrets.APPSTORE_ISSUER_ID }}
        run: |
          IPA=$(ls "$RUNNER_TEMP"/ipa/*.ipa | head -1)
          xcrun altool --upload-app -f "$IPA" -t ios \
            --apiKey "$KEY_ID" --apiIssuer "$ISSUER_ID"
          echo "Subida completada. La compilación tarda unos minutos en aparecer en TestFlight."

      - name: Borrar la clave
        if: always()
        run: rm -rf ~/private_keys ~/.appstoreconnect
'''

EXPORT_OPTIONS = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>destination</key>
    <string>export</string>
    <key>teamID</key>
    <string>__TEAM_ID__</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>uploadSymbols</key>
    <true/>
    <key>manageAppVersionAndBuildNumber</key>
    <false/>
</dict>
</plist>
'''

GITATTRIBUTES = """# Los archivos del proyecto deben viajar con saltos de línea Unix:
# el flujo se ejecuta en macOS y bash falla si el YAML lleva saltos de Windows.
* text=auto eol=lf
*.png binary
"""

GITIGNORE = '''# Xcode
build/
DerivedData/
*.xcarchive
*.ipa
*.dSYM.zip
xcuserdata/
*.xcuserstate

# Claves: nunca subas esto al repositorio
*.p8
*.p12
*.mobileprovision
'''


# ────────────────────────────────────────────────────────────────────────────
#  Info.plist
# ────────────────────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────────────────────
#  AdMob (opcional)
#
#  Identificadores de prueba de Google. Sirven para desarrollar sin arriesgar
#  la cuenta: pulsar tus propios anuncios reales es motivo de cierre inmediato.
# ────────────────────────────────────────────────────────────────────────────

ADMOB_TEST_APP = "ca-app-pub-3940256099942544~1458002511"
ADMOB_TEST_BANNER = "ca-app-pub-3940256099942544/2934735716"
ADMOB_TEST_INTER = "ca-app-pub-3940256099942544/4411468910"

ADS_SWIFT_ON = '''/// Banner de 320x50 anclado abajo. No se superpone al contenido: la web
/// ocupa el resto de la pantalla, así que no hace falta tocar el HTML.
struct AdBanner: View {
    var body: some View {
        BannerContainer()
            .frame(height: 50)
            .background(Color(Cfg.bgColor))
    }
}

struct BannerContainer: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let banner = BannerView(adSize: AdSizeBanner)
        banner.adUnitID = Cfg.bannerUnitID
        banner.rootViewController = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first?.keyWindow?.rootViewController
        banner.load(Request())
        return banner
    }

    func updateUIView(_ uiView: UIView, context: Context) {}
}

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
'''

ADS_SWIFT_OFF = '''/// Sin anuncios: el banner no ocupa espacio y el coordinador no hace nada,
/// así Native.interstitial() puede llamarse desde la web sin romper nada.
struct AdBanner: View {
    var body: some View { EmptyView() }
}

final class AdCoordinator {
    static let shared = AdCoordinator()
    func precargar() {}
    func momentoOportuno() {}
}

func startAds() {}
'''


def ads_pbx(ids, on):
    """Devuelve los cinco fragmentos que necesita el pbxproj."""
    if not on:
        return {"ADS_BUILDFILE": "", "ADS_FRAMEWORK": "", "ADS_PKG_REFS": "",
                "ADS_PKG_PRODS": "", "ADS_SECTIONS": ""}
    pkg, prod, bf = ids["ADS_PKG"], ids["ADS_PROD"], ids["ADS_BF"]
    ref = 'XCRemoteSwiftPackageReference "swift-package-manager-google-mobile-ads"'
    return {
        "ADS_BUILDFILE":
            f"\t\t{bf} /* GoogleMobileAds in Frameworks */ = "
            f"{{isa = PBXBuildFile; productRef = {prod} /* GoogleMobileAds */; }};\n",
        "ADS_FRAMEWORK":
            f"\t\t\t\t{bf} /* GoogleMobileAds in Frameworks */,\n",
        "ADS_PKG_REFS":
            f"\t\t\tpackageReferences = (\n\t\t\t\t{pkg} /* {ref} */,\n\t\t\t);\n",
        "ADS_PKG_PRODS":
            f"\t\t\tpackageProductDependencies = (\n\t\t\t\t{prod} /* GoogleMobileAds */,\n\t\t\t);\n",
        "ADS_SECTIONS": f'''
/* Begin XCRemoteSwiftPackageReference section */
\t\t{pkg} /* {ref} */ = {{
\t\t\tisa = XCRemoteSwiftPackageReference;
\t\t\trepositoryURL = "https://github.com/googleads/swift-package-manager-google-mobile-ads.git";
\t\t\trequirement = {{
\t\t\t\tkind = versionRange;
\t\t\t\tminimumVersion = 12.0.0;
\t\t\t\tmaximumVersion = 99.0.0;
\t\t\t}};
\t\t}};
/* End XCRemoteSwiftPackageReference section */

/* Begin XCSwiftPackageProductDependency section */
\t\t{prod} /* GoogleMobileAds */ = {{
\t\t\tisa = XCSwiftPackageProductDependency;
\t\t\tpackage = {pkg} /* {ref} */;
\t\t\tproductName = GoogleMobileAds;
\t\t}};
/* End XCSwiftPackageProductDependency section */
''',
    }


def build_info_plist(cfg):
    orient = {
        "portrait": ["UIInterfaceOrientationPortrait"],
        "landscape": ["UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
        "all": ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationPortraitUpsideDown",
                "UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
    }[cfg["orientation"]]

    orient_xml = "\n".join(f"\t\t<string>{o}</string>" for o in orient)
    ipad_orient = ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationPortraitUpsideDown",
                   "UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"]
    ipad_xml = "\n".join(f"\t\t<string>{o}</string>" for o in
                         (ipad_orient if cfg["orientation"] == "all" else orient))

    ats = ""
    if cfg["remote_url"].startswith("http://"):
        ats = """	<key>NSAppTransportSecurity</key>
	<dict>
		<key>NSAllowsArbitraryLoads</key>
		<true/>
	</dict>
"""

    ads = ""
    if cfg["ads"]:
        ads = f"""	<key>GADApplicationIdentifier</key>
	<string>{cfg["admob_app_id"]}</string>
	<key>NSUserTrackingUsageDescription</key>
	<string>Se usa para mostrarte anuncios más relevantes. Podés negarlo y la app funciona igual.</string>
	<key>SKAdNetworkItems</key>
	<array>
		<dict>
			<key>SKAdNetworkIdentifier</key>
			<string>cstr6suwn9.skadnetwork</string>
		</dict>
	</array>
"""

    style = {"light": "UIStatusBarStyleLightContent",
             "dark": "UIStatusBarStyleDarkContent",
             "auto": "UIStatusBarStyleDefault"}[cfg["status_bar"]]

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>$(DEVELOPMENT_LANGUAGE)</string>
	<key>CFBundleDisplayName</key>
	<string>{cfg["display_name"]}</string>
	<key>CFBundleExecutable</key>
	<string>$(EXECUTABLE_NAME)</string>
	<key>CFBundleIdentifier</key>
	<string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>$(PRODUCT_NAME)</string>
	<key>CFBundlePackageType</key>
	<string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
	<key>CFBundleShortVersionString</key>
	<string>$(MARKETING_VERSION)</string>
	<key>CFBundleVersion</key>
	<string>{cfg["build"]}</string>
	<key>LSRequiresIPhoneOS</key>
	<true/>
	<key>ITSAppUsesNonExemptEncryption</key>
	<false/>
	<key>UIApplicationSceneManifest</key>
	<dict>
		<key>UIApplicationSupportsMultipleScenes</key>
		<false/>
	</dict>
	<key>UILaunchScreen</key>
	<dict>
		<key>UIColorName</key>
		<string>LaunchBackground</string>
	</dict>
	<key>UIStatusBarStyle</key>
	<string>{style}</string>
	<key>UIViewControllerBasedStatusBarAppearance</key>
	<true/>
	<key>UIRequiresFullScreen</key>
	<false/>
	<key>UISupportedInterfaceOrientations</key>
	<array>
{orient_xml}
	</array>
	<key>UISupportedInterfaceOrientations~ipad</key>
	<array>
{ipad_xml}
	</array>
{ads}{ats}</dict>
</plist>
'''


# ────────────────────────────────────────────────────────────────────────────
#  catálogo de recursos
# ────────────────────────────────────────────────────────────────────────────

def color_set(rgb):
    r, g, b = rgb
    return json.dumps({
        "colors": [{
            "color": {
                "color-space": "srgb",
                "components": {
                    "alpha": "1.000",
                    "blue": f"0x{b:02X}",
                    "green": f"0x{g:02X}",
                    "red": f"0x{r:02X}",
                },
            },
            "idiom": "universal",
        }],
        "info": {"author": "html2ios", "version": 1},
    }, indent=2)


# ────────────────────────────────────────────────────────────────────────────
#  PNG en Python puro
#
#  Existe para que la herramienta funcione en iPhone (a-Shell sólo instala
#  paquetes de Python puro, así que Pillow no está disponible) y en cualquier
#  equipo sin Pillow. Si Pillow existe, se usa porque da mejor calidad.
# ────────────────────────────────────────────────────────────────────────────

def _png_chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def png_write(path, w, h, rows):
    """rows: lista de h bytearrays de w*3 bytes (RGB, sin transparencia)."""
    raw = bytearray()
    for r in rows:
        raw.append(0)          # filtro «ninguno» en cada línea
        raw.extend(r)
    blob = (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _png_chunk(b"IEND", b""))
    Path(path).write_bytes(blob)


def png_read(path, bg=(0, 0, 0)):
    """Devuelve (ancho, alto, filas RGB) o None si el formato no está soportado.

    Admite PNG de 8 bits sin entrelazar, en escala de grises, color indexado,
    RGB y RGBA. La transparencia se compone sobre bg, porque Apple rechaza los
    iconos con canal alfa.
    """
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None

    pos, idat, plte, w, h, depth, ctype, interlace = 8, bytearray(), None, 0, 0, 0, 0, 0
    while pos + 8 <= len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE":
            plte = body
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if depth not in (1, 2, 4, 8, 16) or interlace != 0 or channels is None or not idat:
        return None
    if ctype == 3 and plte is None:
        return None
    if depth != 8 and ctype in (2, 4, 6) and depth != 16:
        return None            # color y alfa sólo existen a 8 o 16 bits

    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None

    bpp = max(1, (channels * depth) // 8)      # bytes por píxel, para el filtrado
    stride = (w * channels * depth + 7) // 8
    if len(raw) < (stride + 1) * h:
        return None

    def muestras(line):
        """Convierte una línea cruda en w*channels valores.

        A 8 bits van tal cual; a 16 nos quedamos con el byte alto; por debajo de
        8 desempaquetamos los bits. Los índices de paleta no se escalan, el resto
        sí, para que el gris quede en 0-255.
        """
        if depth == 8:
            return line
        if depth == 16:
            return line[0::2]
        vals, por_byte, mascara = [], 8 // depth, (1 << depth) - 1
        escala = 255 // mascara
        total = w * channels
        for i in range(total):
            byte = line[i // por_byte]
            desp = 8 - depth * (i % por_byte + 1)
            v = (byte >> desp) & mascara
            vals.append(v if ctype == 3 else v * escala)
        return vals

    filas, prev, p = [], bytearray(stride), 0
    for _ in range(h):
        ftype = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        c = bpp
        if ftype == 1:
            for i in range(c, stride):
                line[i] = (line[i] + line[i - c]) & 255
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ftype == 3:
            for i in range(stride):
                a = line[i - c] if i >= c else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                a = line[i - c] if i >= c else 0
                b = prev[i]
                cc = prev[i - c] if i >= c else 0
                est = a + b - cc
                pa, pb, pc = abs(est - a), abs(est - b), abs(est - cc)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else cc)
                line[i] = (line[i] + pred) & 255
        prev = line
        s = muestras(line)

        # pasar a RGB, componiendo la transparencia sobre el fondo
        rgb = bytearray(w * 3)
        for x in range(w):
            if ctype == 0:
                g = s[x]; r_, g_, b_, a_ = g, g, g, 255
            elif ctype == 4:
                g = s[x * 2]; r_, g_, b_, a_ = g, g, g, s[x * 2 + 1]
            elif ctype == 2:
                r_, g_, b_ = s[x * 3], s[x * 3 + 1], s[x * 3 + 2]; a_ = 255
            elif ctype == 6:
                r_, g_, b_, a_ = s[x * 4], s[x * 4 + 1], s[x * 4 + 2], s[x * 4 + 3]
            else:  # indexado
                idx = s[x] * 3
                if idx + 2 >= len(plte):
                    return None
                r_, g_, b_ = plte[idx], plte[idx + 1], plte[idx + 2]; a_ = 255
            if a_ != 255:
                k = a_ / 255
                r_ = int(r_ * k + bg[0] * (1 - k))
                g_ = int(g_ * k + bg[1] * (1 - k))
                b_ = int(b_ * k + bg[2] * (1 - k))
            rgb[x * 3], rgb[x * 3 + 1], rgb[x * 3 + 2] = r_, g_, b_
        filas.append(rgb)

    return w, h, filas


def png_resize(src_w, src_h, filas, dst):
    """Redimensiona a dst x dst promediando por cajas (nítido al reducir)."""
    # con orígenes enormes, primero un salto entero para acotar el trabajo
    salto = max(1, min(src_w, src_h) // (dst * 2))
    if salto > 1:
        filas = [filas[y] for y in range(0, src_h, salto)]
        nuevas = []
        for r in filas:
            nr = bytearray()
            for x in range(0, src_w, salto):
                nr += r[x * 3:x * 3 + 3]
            nuevas.append(nr)
        filas = nuevas
        src_w, src_h = len(filas[0]) // 3, len(filas)

    salida = []
    for y in range(dst):
        y0, y1 = y * src_h // dst, max(y * src_h // dst + 1, (y + 1) * src_h // dst)
        fila = bytearray(dst * 3)
        for x in range(dst):
            x0, x1 = x * src_w // dst, max(x * src_w // dst + 1, (x + 1) * src_w // dst)
            tr = tg = tb = n = 0
            for yy in range(y0, y1):
                r = filas[yy]
                for xx in range(x0, x1):
                    i = xx * 3
                    tr += r[i]; tg += r[i + 1]; tb += r[i + 2]; n += 1
            fila[x * 3] = tr // n
            fila[x * 3 + 1] = tg // n
            fila[x * 3 + 2] = tb // n
        salida.append(fila)
    return salida


# Tipografía de 5x7 para el icono provisional
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
}


def icono_puro(dest, letras, rgb):
    """Genera un icono de 1024x1024 sin ninguna dependencia externa."""
    N = 1024
    r0, g0, b0 = rgb
    # degradado vertical suave
    filas = []
    for y in range(N):
        k = 1 - (y / N) * 0.38
        r, g, b = int(r0 * k), int(g0 * k), int(b0 * k)
        filas.append(bytearray([r, g, b] * N))

    letras = [c for c in letras.upper() if c in FONT][:2] or ["A"]
    ancho_celda = len(letras) * 5 + (len(letras) - 1)     # 1 columna de separación
    escala = int(N * 0.52) // max(ancho_celda, 7)
    total_w = ancho_celda * escala
    total_h = 7 * escala
    ox, oy = (N - total_w) // 2, (N - total_h) // 2

    for i, ch in enumerate(letras):
        base = ox + i * 6 * escala
        for fy, linea in enumerate(FONT[ch]):
            for fx, bit in enumerate(linea):
                if bit != "1":
                    continue
                for y in range(oy + fy * escala, oy + (fy + 1) * escala):
                    fila = filas[y]
                    for x in range(base + fx * escala, base + (fx + 1) * escala):
                        fila[x * 3] = fila[x * 3 + 1] = fila[x * 3 + 2] = 255
    png_write(dest, N, N, filas)


def png_info(path):
    """(ancho, alto, profundidad, tipo_color, tiene_transparencia) o None."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, w, h, depth, ctype, trns = 8, 0, 0, 0, 0, False
    while pos + 8 <= len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", data[pos + 8:pos + 18])
        elif tag == b"tRNS":
            trns = True
        elif tag == b"IEND":
            break
        pos += 12 + ln
    return w, h, depth, ctype, (trns or ctype in (4, 6))


def buscar_icono(entrada):
    """Busca un icono con nombre habitual junto a la web o en la carpeta actual.

    Existe porque es muy fácil tener el icono al lado y olvidarse de --icon,
    y acabar publicando con el provisional de las iniciales.
    """
    nombres = ["icon", "icono", "appicon", "app-icon", "logo", "ícono"]
    exts = [".png", ".jpg", ".jpeg"]
    carpetas = []
    src = Path(entrada)
    carpetas.append(src if src.is_dir() else src.parent)
    if Path.cwd() not in carpetas:
        carpetas.append(Path.cwd())

    for carpeta in carpetas:
        if not carpeta.exists():
            continue
        for archivo in sorted(carpeta.iterdir()):
            if not archivo.is_file():
                continue
            base = archivo.stem.lower()
            if base in nombres and archivo.suffix.lower() in exts:
                return archivo
    return None


def make_icon(dest, name, rgb, source=None):
    """Deja un icono de 1024x1024 en dest. Devuelve un aviso, o None si todo fue bien."""
    if source:
        src = Path(source)
        if not src.exists():
            die(f"no encuentro el icono: {source}")

        info = png_info(src) if src.suffix.lower() == ".png" else None

        # Copia directa sólo si ya está perfecto: tamaño exacto y sin transparencia.
        # Apple rechaza cualquier icono con canal alfa, así que el resto hay que
        # reprocesarlo aunque mida 1024x1024.
        if info and (info[0], info[1]) == (1024, 1024) and not info[4]:
            shutil.copy(src, dest)
            return None

        tenia_alfa = bool(info and info[4])
        mal_tamano = not info or (info[0], info[1]) != (1024, 1024)

        # 1) Pillow si está disponible: mejor calidad y admite cualquier formato
        try:
            from PIL import Image
            img = Image.open(src)
            if img.mode in ("RGBA", "LA", "P"):
                fondo = Image.new("RGB", img.size, rgb)
                img = img.convert("RGBA")
                fondo.paste(img, mask=img.split()[-1])
                img = fondo
            else:
                img = img.convert("RGB")
            if img.size != (1024, 1024):
                img = img.resize((1024, 1024), Image.LANCZOS)
            img.save(dest, "PNG")
            return ("el icono tenía transparencia: se rellenó con el color de fondo, "
                    "porque Apple no admite canal alfa.") if tenia_alfa else None
        except ImportError:
            pass

        # 2) sin Pillow: sólo PNG, con nuestro propio códec
        if src.suffix.lower() != ".png":
            die(f"sin Pillow sólo puedo leer PNG, y el icono es {src.suffix}.\n"
                "         Convertilo a PNG, o instalá Pillow con:  pip install Pillow")
        leido = png_read(src, rgb)
        if leido is None:
            die("no pude leer ese PNG: es entrelazado, o usa un formato poco común.\n"
                "         Volvé a exportarlo como PNG normal,\n"
                "         o instalá Pillow con:  pip install Pillow")
        w, h, filas = leido
        if (w, h) != (1024, 1024):
            filas = png_resize(w, h, filas, 1024)
        png_write(dest, 1024, 1024, filas)

        avisos = []
        if mal_tamano:
            avisos.append(f"redimensionado de {w}x{h} a 1024x1024")
        if tenia_alfa:
            avisos.append("se rellenó la transparencia con el color de fondo")
        return ("icono ajustado: " + " y ".join(avisos) +
                ". Revisá que se vea bien.") if avisos else None

    # sin icono propio: uno provisional con las iniciales
    iniciales = "".join(w[0] for w in re.split(r"\s+", name.strip()) if w)[:2]
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1024, 1024), rgb)
        d = ImageDraw.Draw(img)
        for y in range(1024):
            k = 1 - (y / 1024) * 0.38
            d.line([(0, y), (1024, y)], fill=tuple(int(c * k) for c in rgb))
        fuente = None
        for ruta in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                     "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                     "/Library/Fonts/Arial Bold.ttf",
                     "C:\\Windows\\Fonts\\arialbd.ttf",
                     "C:\\Windows\\Fonts\\segoeuib.ttf",
                     "C:\\Windows\\Fonts\\calibrib.ttf"]:
            if Path(ruta).exists():
                fuente = ImageFont.truetype(ruta, 420)
                break
        if fuente is None:
            raise ImportError            # sin tipografía, mejor la vía pura
        texto = (iniciales or "A").upper()
        caja = d.textbbox((0, 0), texto, font=fuente)
        d.text(((1024 - (caja[2] - caja[0])) / 2 - caja[0],
                (1024 - (caja[3] - caja[1])) / 2 - caja[1]),
               texto, font=fuente, fill=(255, 255, 255))
        img.save(dest, "PNG")
    except ImportError:
        icono_puro(dest, iniciales or "A", rgb)

    return ("no encontré ningún icono, así que generé uno provisional con las "
            "iniciales. Poné el tuyo con --icon, o dejá en la carpeta un archivo "
            "llamado icono.png y se usará solo.")


# ────────────────────────────────────────────────────────────────────────────
#  comprobación del proyecto generado
# ────────────────────────────────────────────────────────────────────────────

def verify(root, name, cfg):
    """Revisa que el proyecto esté completo y que el pbxproj no tenga referencias sueltas."""
    problems = []

    esperados = [
        f"{name}.xcodeproj/project.pbxproj",
        f"{name}.xcodeproj/project.xcworkspace/contents.xcworkspacedata",
        f"{name}.xcodeproj/xcshareddata/xcschemes/{name}.xcscheme",
        f"{name}/AppMain.swift",
        f"{name}/Info.plist",
        f"{name}/Assets.xcassets/Contents.json",
        f"{name}/Assets.xcassets/AppIcon.appiconset/Contents.json",
        f"{name}/Assets.xcassets/AppIcon.appiconset/icon-1024.png",
        f"{name}/Assets.xcassets/AccentColor.colorset/Contents.json",
        f"{name}/Assets.xcassets/LaunchBackground.colorset/Contents.json",
        f"{name}/www/{cfg['index']}",
        "ExportOptions.plist",
        ".gitignore",
        ".gitattributes",
    ]
    if cfg["workflow"]:
        esperados.append(".github/workflows/ios.yml")

    for rel in esperados:
        if not (root / rel).exists():
            problems.append(f"falta el archivo {rel}")

    icono = root / f"{name}/Assets.xcassets/AppIcon.appiconset/icon-1024.png"
    if icono.exists():
        medida = png_size(icono)
        if medida != (1024, 1024):
            problems.append(f"el icono mide {medida} y Apple exige 1024x1024")

    pbx = (root / f"{name}.xcodeproj/project.pbxproj").read_text()

    if pbx.count("{") != pbx.count("}"):
        problems.append("las llaves del project.pbxproj no están equilibradas")
    if "@@" in pbx:
        problems.append("quedaron marcadores sin sustituir en el project.pbxproj")

    definidos = set(re.findall(r"^\t\t([0-9A-F]{24}) ", pbx, re.M))
    usados = set(re.findall(r"\b([0-9A-F]{24})\b", pbx))
    sueltos = usados - definidos
    if sueltos:
        problems.append(f"referencias sin definir en el pbxproj: {', '.join(sorted(sueltos))}")

    if cfg["ads"]:
        if "XCRemoteSwiftPackageReference" not in pbx:
            problems.append("los anuncios están activados pero falta la dependencia del SDK")
        if "GADApplicationIdentifier" not in (root / f"{name}/Info.plist").read_text():
            problems.append("falta GADApplicationIdentifier en el Info.plist")
        swift_ads = (root / f"{name}/AppMain.swift").read_text()
        if "BannerView" not in swift_ads:
            problems.append("falta el código del banner en AppMain.swift")
        if cfg["admob_inter"] and "InterstitialAd" not in swift_ads:
            problems.append("falta el código del intersticial en AppMain.swift")
        for prueba in ("3940256099942544",):
            if prueba in swift_ads and not cfg.get("es_prueba"):
                problems.append("quedó un identificador de prueba en el código")

    swift = (root / f"{name}/AppMain.swift").read_text()
    if "@@" in swift:
        problems.append("quedaron marcadores sin sustituir en AppMain.swift")

    return problems


# ────────────────────────────────────────────────────────────────────────────
#  generación
# ────────────────────────────────────────────────────────────────────────────

def generate(cfg):
    name = cfg["target"]
    root = Path(cfg["out"])

    if root.exists() and any(root.iterdir()):
        if not cfg["force"]:
            die(f"la carpeta {root} ya existe y no está vacía. Usá --force para sobrescribirla.")
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    app_dir = root / name
    proj_dir = root / f"{name}.xcodeproj"

    # ── 1. copiar la web ──────────────────────────────────────────────────
    www = app_dir / "www"
    www.mkdir(parents=True, exist_ok=True)
    src = Path(cfg["input"])
    if src.is_dir():
        for item in src.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_dir():
                shutil.copytree(item, www / item.name)
            else:
                shutil.copy2(item, www / item.name)
    else:
        shutil.copy2(src, www / cfg["index"])

    archivos = sum(1 for _ in www.rglob("*") if _.is_file())
    peso = sum(f.stat().st_size for f in www.rglob("*") if f.is_file())

    # ── 2. identificadores del proyecto ───────────────────────────────────
    ids = {k: uid(cfg["bundle_id"], k) for k in [
        "BF_SWIFT", "BF_ASSETS", "BF_WWW", "FR_APP", "FR_SWIFT", "FR_ASSETS",
        "FR_INFO", "FR_WWW", "FRAMEWORKS", "GROUP_ROOT", "GROUP_APP",
        "GROUP_PRODUCTS", "TARGET", "PROJECT", "RESOURCES", "SOURCES",
        "CONF_PROJ_DEBUG", "CONF_PROJ_RELEASE", "CONF_TARGET_DEBUG",
        "CONF_TARGET_RELEASE", "CONFLIST_PROJECT", "CONFLIST_TARGET",
        "ADS_PKG", "ADS_PROD", "ADS_BF"]}

    dev_team = f'DEVELOPMENT_TEAM = "{cfg["team"]}";\n\t\t\t\t' if cfg["team"] else ""

    pbx = PBXPROJ
    for key, value in ads_pbx(ids, cfg["ads"]).items():
        pbx = pbx.replace(f"@@{key}@@", value)
    for key, value in ids.items():
        pbx = pbx.replace(f"@@{key}@@", value)
    pbx = (pbx.replace("@@NAME@@", name)
              .replace("@@BUNDLE_ID@@", cfg["bundle_id"])
              .replace("@@VERSION@@", cfg["version"])
              .replace("@@BUILD@@", str(cfg["build"]))
              .replace("@@MIN_IOS@@", cfg["min_ios"])
              .replace("@@DEVICES@@", cfg["devices"])
              .replace("@@DEV_TEAM@@", dev_team))
    write(proj_dir / "project.pbxproj", pbx)

    write(proj_dir / "project.xcworkspace" / "contents.xcworkspacedata", WORKSPACE)
    write(proj_dir / "xcshareddata" / "xcschemes" / f"{name}.xcscheme",
          XCSCHEME.replace("@@TARGET@@", ids["TARGET"]).replace("@@NAME@@", name))

    # ── 3. código Swift ───────────────────────────────────────────────────
    r, g, b = cfg["rgb"]
    swift = (SWIFT_APP
             .replace("@@REMOTE_URL@@", cfg["remote_url"])
             .replace("@@INDEX@@", cfg["index"])
             .replace("@@BOUNCE@@", "true" if cfg["bounce"] else "false")
             .replace("@@PULL@@", "true" if cfg["pull_refresh"] else "false")
             .replace("@@EXTERNAL@@", cfg["external"])
             .replace("@@BG_R@@", f"{r/255:.3f}")
             .replace("@@BG_G@@", f"{g/255:.3f}")
             .replace("@@BG_B@@", f"{b/255:.3f}")
             .replace("@@ADS_IMPORTS@@",
                      "import GoogleMobileAds\nimport AppTrackingTransparency"
                      if cfg["ads"] else "")
             .replace("@@ADS_BANNER_ID@@", cfg["admob_banner"])
             .replace("@@ADS_INTER_ID@@", cfg["admob_inter"])
             .replace("@@ADS_INTER_EVERY@@", str(cfg["inter_every"]))
             .replace("@@ADS_INTER_AFTER@@", str(cfg["inter_after"]))
             .replace("@@ADS_INTER_ONCE@@", "true" if cfg["inter_once"] else "false")
             .replace("@@ADS_CODE@@", ADS_SWIFT_ON if cfg["ads"] else ADS_SWIFT_OFF))
    write(app_dir / "AppMain.swift", swift)

    # ── 4. Info.plist y recursos ──────────────────────────────────────────
    write(app_dir / "Info.plist", build_info_plist(cfg))

    assets = app_dir / "Assets.xcassets"
    write(assets / "Contents.json",
          json.dumps({"info": {"author": "html2ios", "version": 1}}, indent=2))
    write(assets / "AccentColor.colorset" / "Contents.json", color_set(cfg["rgb"]))
    write(assets / "LaunchBackground.colorset" / "Contents.json", color_set(cfg["rgb"]))
    write(assets / "AppIcon.appiconset" / "Contents.json", json.dumps({
        "images": [{"filename": "icon-1024.png", "idiom": "universal",
                    "platform": "ios", "size": "1024x1024"}],
        "info": {"author": "html2ios", "version": 1},
    }, indent=2))
    (assets / "AppIcon.appiconset").mkdir(parents=True, exist_ok=True)

    icono = cfg["icon"]
    encontrado = None
    if not icono:
        encontrado = buscar_icono(cfg["input"])
        if encontrado:
            icono = str(encontrado)

    aviso_icono = make_icon(assets / "AppIcon.appiconset" / "icon-1024.png",
                            cfg["display_name"], cfg["rgb"], icono)
    if encontrado:
        aviso_icono = (f"se usó el icono encontrado en la carpeta: {encontrado.name}"
                       + (f" ({aviso_icono})" if aviso_icono else ""))

    # ── 5. exportación, flujo y documentación ─────────────────────────────
    write(root / "ExportOptions.plist", EXPORT_OPTIONS)
    write(root / ".gitignore", GITIGNORE)
    write(root / ".gitattributes", GITATTRIBUTES)

    if cfg["workflow"]:
        wf = (WORKFLOW.replace("@@NAME@@", name)
                      .replace("@@BUNDLE_ID@@", cfg["bundle_id"])
                      .replace("@@BUILD@@", str(cfg["build"])))
        write(root / ".github" / "workflows" / "ios.yml", wf)

    write(root / "LEEME.md", readme(cfg, name, archivos, peso))

    return {"root": root, "name": name, "archivos": archivos,
            "peso": peso, "aviso_icono": aviso_icono}


def readme(cfg, name, archivos, peso):
    return f"""# {cfg["display_name"]} — proyecto iOS

Generado con html2ios. Contiene una app nativa que muestra tu página web
empaquetada dentro del binario, así que **funciona sin conexión**.

| | |
|---|---|
| Nombre | {cfg["display_name"]} |
| Identificador | `{cfg["bundle_id"]}` |
| Versión | {cfg["version"]} (build {cfg["build"]}) |
| iOS mínimo | {cfg["min_ios"]} |
| Archivos web | {archivos} ({peso/1024:.0f} KB) |
| Origen | {"remoto: " + cfg["remote_url"] if cfg["remote_url"] else "archivos empaquetados"} |

---

## Antes de nada

Necesitás **una cuenta del Apple Developer Program**: 99 dólares al año, en
<https://developer.apple.com/programs/>. La aprobación tarda entre unas horas y
dos días. No hay forma de publicar en la App Store sin ella.

No necesitás un Mac: todo lo demás se hace desde el navegador.

---

## Paso 1 · Crear la app en App Store Connect

1. Entrá en <https://appstoreconnect.apple.com> → **Mis apps** → **+** → **Nueva app**.
2. Plataforma: iOS. Nombre: el que verá la gente en la tienda.
3. **ID del paquete**: tiene que coincidir exactamente con `{cfg["bundle_id"]}`.
   Si no aparece en la lista, crealo primero en
   <https://developer.apple.com/account/resources/identifiers/list>.
4. SKU: cualquier código interno, por ejemplo `{name.lower()}-001`.

## Paso 2 · Crear la clave de API

Esta clave es lo que permite compilar sin Mac: `xcodebuild` la usa para crear
por su cuenta los certificados y perfiles que hacen falta.

1. App Store Connect → **Usuarios y acceso** → **Integraciones** → **Claves** →
   **App Store Connect API** → **+**.
2. Rol: **App Manager** (necesita ese nivel para poder crear certificados).
3. Descargá el archivo `.p8`. **Sólo se puede descargar una vez.**
4. Anotá el **Key ID** y el **Issuer ID** que aparecen en esa pantalla.
5. Anotá también tu **Team ID**, en
   <https://developer.apple.com/account> → Membresía.

## Paso 3 · Subir el proyecto a GitHub

```bash
cd "{name}"          # la carpeta que generó html2ios
git init
git add .
git commit -m "Primera versión"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/TU-REPO.git
git push -u origin main
```

> Si el repositorio es **público**, los minutos de compilación en macOS son
> gratuitos. Si es privado, consumen cuota y cuestan diez veces más que los de
> Linux; para un proyecto pequeño igualmente entra en el plan gratuito, pero
> conviene saberlo.

## Paso 4 · Guardar los secretos

En tu repositorio: **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Creá estos cuatro:

| Nombre | Contenido |
|---|---|
| `APPSTORE_KEY_ID` | El Key ID (10 caracteres, tipo `A1B2C3D4E5`) |
| `APPSTORE_ISSUER_ID` | El Issuer ID (un UUID largo) |
| `APPSTORE_PRIVATE_KEY` | El contenido **completo** del archivo `.p8`, incluidas las líneas `-----BEGIN PRIVATE KEY-----` y `-----END PRIVATE KEY-----` |
| `APPLE_TEAM_ID` | Tu Team ID (10 caracteres) |

Para copiar el `.p8` entero, abrilo con un editor de texto plano.
**No lo subas nunca al repositorio**: el `.gitignore` ya lo bloquea.

## Paso 5 · Compilar

En GitHub: pestaña **Actions** → *Compilar y subir a App Store Connect* →
**Run workflow**.

Tarda entre diez y veinte minutos. Cuando termina, la compilación aparece en
App Store Connect → tu app → **TestFlight**. Ahí podés instalarla en tu iPhone
antes de publicarla.

Cada ejecución sube automáticamente el número de build, porque Apple rechaza
dos envíos con el mismo número.

## Paso 6 · Enviar a revisión

En App Store Connect, en la ficha de tu app, hace falta:

- **Capturas de pantalla**: obligatorias para iPhone de 6,9 pulgadas
  (1320×2868). Podés sacarlas desde TestFlight en tu iPhone.
- **Descripción, palabras clave y categoría**.
- **URL de política de privacidad**: obligatoria siempre, aunque tu app no
  recoja ningún dato. Puede ser una página sencilla en GitHub Pages.
- **Privacidad de la app**: si no recogés datos, respondé que no recogés datos.
- **Clasificación por edades**.

Luego, **Añadir para revisión**. La revisión suele tardar entre uno y tres días.

---

## El riesgo real de esta app: la norma 4.2

Apple rechaza las apps que son sólo una web envuelta. La norma 4.2 del
reglamento de revisión dice que una app debe ofrecer algo más que una página
web reempaquetada. Es, de lejos, el motivo de rechazo más habitual para
proyectos como este.

Lo que ya juega a tu favor en este proyecto:

- **Funciona sin conexión.** Los archivos van dentro del binario, no se
  descargan. Esto es lo que más distingue una app de un marcador del navegador.
- **No se ve nada de navegador**: ni barra de direcciones, ni botones.
- **Tiene funciones nativas** disponibles desde tu JavaScript.

Lo que conviene que añadas antes de enviarla:

```javascript
// Estas funciones sólo existen dentro de la app; en el navegador no.
if (window.Native) {{
  Native.haptic('light');                       // vibración al pulsar
  Native.share({{ text: 'Mirá esto', url: '…' }}); // menú nativo de compartir
  Native.open('https://ejemplo.com');           // abrir un enlace fuera
}}
```

Usalas de verdad en tu página: vibración al acertar, compartir resultados, etc.
Y en la nota para el revisor explicá qué hace la app y por qué tiene sentido
como app y no como web. Si tu página además existe pública e idéntica en
internet, es probable que te la rechacen; conviene que la app aporte algo que
la web no tenga.

---

## Probar en tu iPhone antes de publicar

No hace falta esperar a la revisión. Una vez subida la compilación, entra en
TestFlight y la instalás en tu propio iPhone en dos minutos.

## Errores frecuentes

| Error | Qué pasa |
|---|---|
| `ITMS-90725: SDK version issue` | Se compiló con un Xcode viejo. El flujo ya comprueba que sea 26 o superior. |
| `No suitable application records were found` | El identificador del paquete no coincide con el de App Store Connect, o la app todavía no está creada allí. |
| `The bundle version must be higher` | Ese número de build ya se subió. Volvé a lanzar el flujo: sube solo. |
| `Authentication credentials are missing` | Alguno de los cuatro secretos está mal copiado, o al `.p8` le faltan las líneas BEGIN/END. |
| `No profiles for '{cfg["bundle_id"]}' were found` | La clave de API no tiene rol App Manager, o el Team ID es incorrecto. |

## Volver a generar

Si cambiás el HTML, volvé a ejecutar html2ios con `--force` y subí los cambios.
Sólo se sobrescribe la carpeta generada, no tu repositorio.
"""


# ────────────────────────────────────────────────────────────────────────────
#  entrada
# ────────────────────────────────────────────────────────────────────────────

def reparar_argumentos(argv, opciones):
    """Separa opciones pegadas al valor anterior por un espacio olvidado.

    Escribir «...~7922270315--admob-banner ca-app-pub...» es un error muy fácil
    de cometer en un comando largo, y argparse sólo responde «unrecognized
    arguments», que no señala dónde está el problema. Aquí lo reparamos y
    avisamos, en vez de hacer perder el rato.
    """
    salida, arreglados = [], []
    for arg in argv:
        if arg.startswith("-") or "--" not in arg:
            salida.append(arg)
            continue
        corte = arg.index("--")
        valor, resto = arg[:corte], arg[corte:]
        nombre = resto.split("=")[0]
        if valor and nombre in opciones:
            salida.extend([valor, resto])
            arreglados.append(nombre)
        else:
            salida.append(arg)
    return salida, arreglados


def main():
    p = argparse.ArgumentParser(
        prog="html2ios",
        description="Convierte una página HTML en un proyecto de Xcode listo para la App Store.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""ejemplos:
  python3 html2ios.py --input pagina.html --name "Mi App" --bundle-id com.midominio.miapp
  python3 html2ios.py --input ./web/ --name "Ahorcado" --bundle-id com.juan.ahorcado \\
                      --bg "#12153F" --icon icono.png --orientation portrait
""")
    p.add_argument("--input", required=True,
                   help="archivo .html o carpeta con la web")
    p.add_argument("--name", required=True,
                   help="nombre visible de la app")
    p.add_argument("--bundle-id", required=True,
                   help="identificador único, tipo com.tudominio.miapp")
    p.add_argument("--out", help="carpeta de salida (por defecto: el nombre de la app)")
    p.add_argument("--index", default="index.html",
                   help="archivo de inicio dentro de la carpeta (por defecto index.html)")
    p.add_argument("--version", default="1.0", help="versión visible (por defecto 1.0)")
    p.add_argument("--build", type=int, default=1, help="número de compilación (por defecto 1)")
    p.add_argument("--icon", help="PNG para el icono; ideal 1024x1024")
    p.add_argument("--bg", default="#111111",
                   help="color de fondo y de la pantalla de carga (por defecto #111111)")
    p.add_argument("--orientation", choices=["portrait", "landscape", "all"], default="portrait")
    p.add_argument("--status-bar", choices=["light", "dark", "auto"], default="light")
    p.add_argument("--min-ios", default="15.0", help="versión mínima de iOS (por defecto 15.0)")
    p.add_argument("--devices", choices=["iphone", "ipad", "both"], default="both")
    p.add_argument("--team", default="", help="Team ID de Apple (opcional aquí; se pasa como secreto)")
    p.add_argument("--url", default="",
                   help="cargar esta dirección en vez de los archivos locales")
    p.add_argument("--external", choices=["inapp", "safari", "same"], default="inapp",
                   help="cómo abrir enlaces externos (por defecto: navegador incrustado)")
    p.add_argument("--bounce", action="store_true",
                   help="permitir el rebote al hacer scroll (por defecto desactivado)")
    p.add_argument("--pull-refresh", action="store_true",
                   help="recargar tirando hacia abajo")
    p.add_argument("--ads-test", action="store_true",
                   help="activa los anuncios con los identificadores de prueba de Google")
    p.add_argument("--admob-app-id", default="",
                   help="ID de aplicación de AdMob (con ~), activa el banner inferior")
    p.add_argument("--admob-banner", default="",
                   help="ID del bloque de banner (con /); si se omite, usa el de prueba")
    p.add_argument("--admob-interstitial", default="",
                   help="ID del bloque intersticial (con /); la web lo pide con Native.interstitial()")
    p.add_argument("--interstitial-every", type=int, default=3, metavar="N",
                   help="mostrar el intersticial uno de cada N avisos (por defecto 3)")
    p.add_argument("--interstitial-after", type=int, default=40, metavar="SEG",
                   help="segundos desde que se abre la app antes del primer intersticial (por defecto 40)")
    p.add_argument("--interstitial-once", action="store_true",
                   help="mostrarlo una sola vez por sesión, hasta que se reabra la app")
    p.add_argument("--no-workflow", action="store_true",
                   help="no generar el flujo de GitHub Actions")
    p.add_argument("--force", action="store_true", help="sobrescribir la carpeta de salida")
    p.add_argument("--version-tool", action="version", version=f"html2ios {VERSION}")

    conocidas = {o for accion in p._actions for o in accion.option_strings}
    argv, arreglados = reparar_argumentos(sys.argv[1:], conocidas)
    a = p.parse_args(argv)
    if arreglados:
        print("\n  AVISO: faltaba un espacio antes de " + ", ".join(arreglados) +
              ".\n  Lo he separado y sigo, pero corregilo en tu comando.")

    # validaciones
    src = Path(a.input)
    if not src.exists():
        die(f"no encuentro la entrada: {a.input}")
    if src.is_dir() and not (src / a.index).exists():
        die(f"la carpeta no contiene {a.index}. Indicá otro con --index.")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9.\-]*[A-Za-z0-9]$", a.bundle_id) or "." not in a.bundle_id:
        die("el identificador debe tener forma de dominio inverso, por ejemplo com.midominio.miapp\n"
            "         (sólo letras, números, puntos y guiones; sin espacios ni acentos)")
    if not re.match(r"^\d+(\.\d+){0,2}$", a.version):
        die("la versión debe ser un número tipo 1.0 o 1.2.3")

    def revisar_id(valor, opcion, sep, ejemplo, donde):
        """Diagnostica por qué un identificador de AdMob no es válido."""
        otro = "/" if sep == "~" else "~"
        if otro in valor:
            die(f"{opcion}: este identificador va con «{sep}», no con «{otro}».\n"
                f"         Tiene esta forma:  {ejemplo}\n"
                f"         Lo sacás de {donde}.")
        if not valor.startswith("ca-app-pub-"):
            die(f"{opcion}: tiene que empezar por «ca-app-pub-».\n"
                f"         Tiene esta forma:  {ejemplo}")
        if re.search(r"[A-Za-z]", valor[len("ca-app-pub-"):]):
            die(f"{opcion}: quedaron letras en el identificador.\n"
                f"         Parece que no reemplazaste las X del ejemplo por tus números.\n"
                f"         Tiene esta forma:  {ejemplo}\n"
                f"         Lo sacás de {donde}.\n"
                f"         Si todavía no tenés cuenta de AdMob, usá --ads-test a secas\n"
                f"         y seguí adelante con anuncios de prueba.")
        die(f"{opcion}: el identificador no tiene la forma esperada.\n"
            f"         Tiene esta forma:  {ejemplo}")

    ads = bool(a.admob_app_id) or a.ads_test
    aviso_ads = None

    if a.ads_test and (a.admob_app_id or a.admob_banner or a.admob_interstitial):
        die("no mezcles --ads-test con identificadores reales.\n"
            "         O bien --ads-test para probar, o bien los tres identificadores tuyos.")

    if a.ads_test:
        a.admob_app_id = ADMOB_TEST_APP
        a.admob_banner = ADMOB_TEST_BANNER
        a.admob_interstitial = ADMOB_TEST_INTER
        aviso_ads = ("MODO DE PRUEBA. Los anuncios llevan la etiqueta «Test» y no generan "
                     "ingresos. No publiques así.")

    if ads:
        if not re.match(r"^ca-app-pub-\d+~\d+$", a.admob_app_id):
            revisar_id(a.admob_app_id, "--admob-app-id", "~",
                       "ca-app-pub-1234567890123456~1234567890",
                       "AdMob → Apps → Configuración de la app")
        if a.admob_banner and not re.match(r"^ca-app-pub-\d+/\d+$", a.admob_banner):
            revisar_id(a.admob_banner, "--admob-banner", "/",
                       "ca-app-pub-1234567890123456/1234567890",
                       "AdMob → Bloques de anuncios → Banner")
        if float(a.min_ios.split(".")[0]) < 14:
            die("los anuncios necesitan iOS 14 o superior por el permiso de seguimiento.\n"
                "         Usá --min-ios 15.0 o quitá --admob-app-id.")
        if a.admob_interstitial and not re.match(r"^ca-app-pub-\d+/\d+$", a.admob_interstitial):
            revisar_id(a.admob_interstitial, "--admob-interstitial", "/",
                       "ca-app-pub-1234567890123456/1234567890",
                       "AdMob → Bloques de anuncios → Intersticial")
        if a.interstitial_every < 1:
            die("--interstitial-every tiene que ser 1 o más.")
        if a.interstitial_every == 1:
            print("\n  ATENCIÓN: con --interstitial-every 1 el anuncio sale en cada aviso.\n"
                  "  AdMob prohíbe las interrupciones excesivas y puede suspender la cuenta.\n"
                  "  Para partidas cortas, 3 o más es lo razonable.\n")
        if a.interstitial_after < 0:
            die("--interstitial-after no puede ser negativo.")
        if a.interstitial_once:
            a.interstitial_every = 1     # el primer momento válido tras la espera

        # Sin relleno automático: un bloque de prueba colado en una versión
        # publicada no daría ni un céntimo y costaría descubrirlo.
        if not a.admob_banner:
            die("falta --admob-banner con tu bloque real.\n"
                "         Lo sacás de AdMob → Bloques de anuncios → Banner.\n"
                "         Si sólo querés probar, usá --ads-test a secas.")
        if not a.admob_interstitial:
            aviso_ads = ("sin --admob-interstitial: el anuncio a pantalla completa queda "
                         "desactivado. Sólo habrá banner.")
    elif a.admob_banner or a.admob_interstitial:
        die("pusiste un bloque de anuncio pero falta --admob-app-id; hacen falta los dos.")

    target = slug(a.name)
    cfg = {
        "input": a.input,
        "display_name": a.name,
        "target": target,
        "bundle_id": a.bundle_id,
        "out": a.out or target,
        "index": a.index,
        "version": a.version,
        "build": a.build,
        "icon": a.icon,
        "rgb": hex_to_rgb(a.bg),
        "orientation": a.orientation,
        "status_bar": a.status_bar,
        "min_ios": a.min_ios,
        "devices": {"iphone": "1", "ipad": "2", "both": "1,2"}[a.devices],
        "team": a.team,
        "remote_url": a.url,
        "external": a.external,
        "bounce": a.bounce,
        "pull_refresh": a.pull_refresh,
        "workflow": not a.no_workflow,
        "force": a.force,
        "ads": ads,
        "admob_app_id": a.admob_app_id,
        "admob_banner": a.admob_banner,
        "admob_inter": a.admob_interstitial,
        "inter_every": a.interstitial_every,
        "inter_after": a.interstitial_after,
        "inter_once": a.interstitial_once,
        "es_prueba": a.ads_test,
    }

    print(f"\n  html2ios {VERSION}\n  {'─' * 52}")
    result = generate(cfg)

    problemas = verify(result["root"], result["name"], cfg)

    info(f"proyecto: {result['root'].resolve()}")
    info(f"web empaquetada: {result['archivos']} archivos, "
         f"{result['peso']/1024:.1f} KB")
    if result["aviso_icono"]:
        info(f"AVISO: {result['aviso_icono']}")
    if cfg["ads"]:
        info("banner de AdMob activado, anclado abajo (50 puntos de alto)")
        if not cfg["admob_inter"]:
            info("intersticial: desactivado")
        elif cfg["inter_once"]:
            info(f"intersticial: una sola vez por sesión, a partir de los "
                 f"{cfg['inter_after']} s desde que se abre la app")
        else:
            info(f"intersticial: uno de cada {cfg['inter_every']} avisos, no antes de "
                 f"{cfg['inter_after']} s desde el arranque, con 60 s entre anuncios")
        if cfg["admob_inter"]:
            info("la web debe llamar a Native.interstitial() al empezar cada partida")
        info(f"identificadores: {cfg['admob_app_id']}")
        if aviso_ads:
            info(f"AVISO: {aviso_ads}")

    if problemas:
        print(f"\n  {'─' * 52}")
        print("  LA COMPROBACIÓN ENCONTRÓ PROBLEMAS:")
        for x in problemas:
            print(f"    · {x}")
        sys.exit(2)

    print(f"  {'─' * 52}")
    info("comprobación superada: el proyecto está completo")
    print(f"""
  Ahora:
    1. Leé {result['root']}/LEEME.md — tiene los seis pasos hasta la tienda.
    2. Creá la app en appstoreconnect.apple.com con el id {cfg['bundle_id']}
    3. Subí esta carpeta a GitHub y guardá los cuatro secretos.
    4. Actions → Run workflow. En 15 minutos la tenés en TestFlight.
""")


if __name__ == "__main__":
    main()
