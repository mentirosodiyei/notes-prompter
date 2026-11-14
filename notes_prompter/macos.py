"""Cocoa UI owned by Tk's main thread; no secondary AppKit event loop."""
from __future__ import annotations

from .i18n import tr

import AppKit
import Foundation
import objc
from WebKit import WKWebView, WKWebViewConfiguration, WKWebsiteDataStore


class MenuActions(Foundation.NSObject):
    @objc.IBAction
    def show_(self, sender):
        self.actions.put("open")

    @objc.IBAction
    def admin_(self, sender):
        self.actions.put("admin")

    @objc.IBAction
    def stop_(self, sender):
        self.actions.put("stop")

    @objc.IBAction
    def quit_(self, sender):
        self.actions.put("exit")


class MacMenu:
    def __init__(self, root):
        self.actions = MenuActions.alloc().init()
        self.actions.actions = root.tray.actions
        self.item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        self.item.button().setTitle_("NP")
        self.item.button().setToolTip_(tr('Notes Prompter · Abrir, parar o salir'))
        self.menu = AppKit.NSMenu.alloc().initWithTitle_("Notes Prompter")
        self.menu.setAutoenablesItems_(False)
        self.configuration_items = []
        for title, action, key in ((tr('Abrir Notes Prompter'), "show:", ""),
                                   (tr('Panel de administración'), "admin:", ""),
                                   (tr('Parar salida'), "stop:", ""),
                                   (tr('Salir de Notes Prompter'), "quit:", "")):
            entry = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            entry.setTarget_(self.actions)
            self.menu.addItem_(entry)
            if action == "admin:":
                self.configuration_items.append(entry)
        self.item.setMenu_(self.menu)
        root.createcommand("tk::mac::ReopenApplication", lambda *args: root._show_window())
        root.createcommand("tk::mac::Quit", lambda *args: root.after_idle(root._close))
        root.bind("<Command-q>", lambda event: root.after_idle(root._close))
        root.bind("<Command-w>", lambda event: root._hide_to_tray())

    def set_configuration_enabled(self, enabled):
        for item in self.configuration_items:
            item.setEnabled_(enabled)

    def close(self):
        AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(self.item)
        self.actions.actions = None


class OutputWindow(AppKit.NSWindow):
    def canBecomeKeyWindow(self):
        return True

    def cancelOperation_(self, sender):
        # Escape remains an obvious way back from a single-screen output.
        self.stop_callback()


class NativeOutput:
    def __init__(self, url, screen, on_stop):
        native = AppKit.NSScreen.screens()
        if screen is None or screen.index >= len(native):
            raise RuntimeError(tr('La pantalla seleccionada ya no está conectada.'))
        self.application = AppKit.NSApplication.sharedApplication()
        frame = native[screen.index].frame()
        self.window = OutputWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
        self.window.stop_callback = on_stop
        self.window.setReleasedWhenClosed_(False)
        self.window.setTitle_(tr('Notes Prompter · Salida'))
        self.window.setBackgroundColor_(AppKit.NSColor.blackColor())
        self.window.setLevel_(AppKit.NSMainMenuWindowLevel + 1)
        # A borderless full-screen window on the selected display, without creating a Space.
        self.window.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
                                           AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary |
                                           AppKit.NSWindowCollectionBehaviorStationary |
                                           AppKit.NSWindowCollectionBehaviorIgnoresCycle)
        config = WKWebViewConfiguration.alloc().init()
        config.setWebsiteDataStore_(WKWebsiteDataStore.nonPersistentDataStore())
        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            Foundation.NSMakeRect(0, 0, frame.size.width, frame.size.height), config)
        self.webview.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self.window.setContentView_(self.webview)
        request = Foundation.NSURLRequest.requestWithURL_(Foundation.NSURL.URLWithString_(url))
        self.webview.loadRequest_(request)
        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(self.webview)

    def close(self):
        self.webview.stopLoading()
        self.webview.loadHTMLString_baseURL_("", None)
        self.window.orderOut_(None)
        self.window.close()
        self.window.stop_callback = None
