# -*- coding: utf-8 -*-
"""
app.py — Interfaccia grafica nativa di FormulaDeck (Cocoa / AppKit, PyObjC).

Ruolo: *post-processore*. La sorgente LaTeX (NSTextView) è l'unica "fonte di
verità" — il vettore-soluzione. Tutto il resto (anteprima KaTeX nella
WKWebView, copia inline $…$ / display $$…$$) è derivato da quella sorgente.
La logica di dominio vive in core.py e non è toccata qui.

Avvio in sviluppo:   python3 app.py
Build bundle .app:   ./build.sh
"""

import os
import sys

import objc
from Cocoa import (
    NSApplication, NSApp, NSObject, NSWindow, NSView, NSTextView,
    NSScrollView, NSButton, NSPopUpButton, NSTextField, NSColor, NSFont,
    NSBezelStyleRounded, NSBezelStyleRegularSquare,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
    NSBackingStoreBuffered, NSMakeRect, NSMakeRange, NSMakeSize,
    NSViewWidthSizable, NSViewHeightSizable, NSViewMinYMargin,
    NSViewMaxXMargin, NSViewMaxYMargin, NSViewMinXMargin, NSPasteboard,
    NSPasteboardTypeString, NSSplitView, NSMenu, NSMenuItem,
    NSApplicationActivationPolicyRegular, NSAlert, NSBezelBorder,
    NSImageView, NSWorkspace,
)
from Foundation import NSURL
from WebKit import WKWebView, WKWebViewConfiguration

import core


# ---------------------------------------------------------------------------
# Funzioni di pura utilità (livello modulo: nessun self -> niente conflitti
# tra il bridge Objective-C e i metodi Python).
# ---------------------------------------------------------------------------

@objc.python_method
def resource_path(*parts):
    """Percorso di una risorsa sia in sviluppo sia dentro il bundle py2app.

    In sviluppo le risorse stanno accanto a questo file; nel bundle finiscono
    in Contents/Resources. NSBundle.resourcePath() le individua in entrambi i
    casi quando l'app è "frozen".
    """
    try:
        from Foundation import NSBundle
        rp = NSBundle.mainBundle().resourcePath()
        candidate = os.path.join(str(rp), *parts)
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


# Dimensioni e costanti di layout -------------------------------------------
WIN_W, WIN_H = 980, 680
SIDEBAR_W = 250
TOOLBAR_H = 52
GRID_COLS = 4
BTN_W, BTN_H = 52, 38
GRID_PAD = 10
GRID_GAP = 6

# Metadati dell'applicazione -------------------------------------------------
APP_NAME = "FormulaDeck"
APP_VERSION = "1.0.0"
APP_AUTHOR = "B. Raucci"
APP_WEBSITE = "https://www.raucci.net"
APP_TAGLINE = "Editor nativo di formule LaTeX"
APP_COPYRIGHT = "© 2025 B. Raucci — Licenza MIT"
APP_BLURB = (
    "Composizione di espressioni LaTeX con anteprima dal vivo.\n"
    "La sorgente è l'unica fonte di verità; l'anteprima\n"
    "(KaTeX, in locale) è il post-processing, ricalcolato a valle."
)


class FlippedView(NSView):
    """NSView con origine in alto a sinistra: comoda per griglie verticali."""
    def isFlipped(self):
        return True


class AppDelegate(NSObject):

    # -- ciclo di vita -------------------------------------------------------
    def applicationDidFinishLaunching_(self, notification):
        self._templates = []      # mappa tag-bottone -> template insert
        self._web_ready = False
        self._build_menu()
        self._build_window()
        self._populate_grid(list(core.PALETTES.keys())[0])
        self._load_preview()
        NSApp.activateIgnoringOtherApps_(True)

    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
        return True

    # -- costruzione del menu (necessario per Cmd+Q, Copia, ecc.) -----------
    @objc.python_method
    def _build_menu(self):
        menubar = NSMenu.alloc().init()
        app_item = NSMenuItem.alloc().init()
        menubar.addItem_(app_item)
        NSApp.setMainMenu_(menubar)
        app_menu = NSMenu.alloc().init()

        about_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Informazioni su FormulaDeck", "showAbout:", "")
        about_item.setTarget_(self)
        app_menu.addItem_(about_item)
        app_menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Esci da FormulaDeck", "terminate:", "q")
        app_menu.addItem_(quit_item)
        app_item.setSubmenu_(app_menu)

    # -- finestra "Informazioni" (About) -----------------------------------
    def showAbout_(self, sender):
        # singola istanza: se già aperta, la porto in primo piano
        if getattr(self, "_aboutWindow", None) is not None:
            self._aboutWindow.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)
            return
        self._build_about()

    def openWebsite_(self, sender):
        url = NSURL.URLWithString_(APP_WEBSITE)
        if url is not None:
            NSWorkspace.sharedWorkspace().openURL_(url)

    @objc.python_method
    def _about_label(self, text, frame, size, color, bold=False, center=True):
        f = NSTextField.alloc().initWithFrame_(frame)
        f.setBezeled_(False)
        f.setEditable_(False)
        f.setSelectable_(False)
        f.setDrawsBackground_(False)
        f.setAlignment_(1 if center else 0)  # 1 = center, 0 = left
        f.setTextColor_(color)
        font = (NSFont.boldSystemFontOfSize_(size) if bold
                else NSFont.systemFontOfSize_(size))
        f.setFont_(font)
        # supporto multi-riga (per il blurb)
        try:
            f.cell().setWraps_(True)
            f.cell().setLineBreakMode_(0)  # wrapping
        except Exception:
            pass
        f.setStringValue_(text)
        return f

    @objc.python_method
    def _build_about(self):
        AW, AH = 420, 500
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, AW, AH), style, NSBackingStoreBuffered, False)
        w.setTitle_("Informazioni")
        w.setReleasedWhenClosed_(False)
        w.setDelegate_(self)
        w.center()
        cv = w.contentView()

        # icona dell'applicazione (nel bundle è la nostra .icns)
        icon = NSApp.applicationIconImage()
        iv = NSImageView.alloc().initWithFrame_(
            NSMakeRect((AW - 128) / 2, AH - 150, 128, 128))
        if icon is not None:
            iv.setImage_(icon)
        cv.addSubview_(iv)

        cv.addSubview_(self._about_label(
            APP_NAME, NSMakeRect(0, AH - 192, AW, 30), 22,
            NSColor.labelColor(), bold=True))
        cv.addSubview_(self._about_label(
            APP_TAGLINE, NSMakeRect(0, AH - 214, AW, 20), 13,
            NSColor.secondaryLabelColor()))
        cv.addSubview_(self._about_label(
            "Versione " + APP_VERSION, NSMakeRect(0, AH - 236, AW, 18), 11,
            NSColor.tertiaryLabelColor()))

        # separatore
        line = NSView.alloc().initWithFrame_(NSMakeRect(60, AH - 256, AW - 120, 1))
        line.setWantsLayer_(True)
        try:
            line.layer().setBackgroundColor_(
                NSColor.separatorColor().CGColor())
        except Exception:
            pass
        cv.addSubview_(line)

        cv.addSubview_(self._about_label(
            APP_AUTHOR, NSMakeRect(0, AH - 290, AW, 22), 15,
            NSColor.labelColor(), bold=True))

        # link al sito (pulsante senza bordo, titolo blu)
        link = NSButton.alloc().initWithFrame_(
            NSMakeRect((AW - 220) / 2, AH - 314, 220, 22))
        link.setBordered_(False)
        link.setTitle_("www.raucci.net")
        link.setTarget_(self)
        link.setAction_("openWebsite:")
        try:
            from Foundation import (NSAttributedString, NSForegroundColorAttributeName,
                                    NSFontAttributeName)
            attrs = {
                NSForegroundColorAttributeName: NSColor.linkColor(),
                NSFontAttributeName: NSFont.systemFontOfSize_(13),
            }
            link.setAttributedTitle_(
                NSAttributedString.alloc().initWithString_attributes_(
                    "www.raucci.net", attrs))
        except Exception:
            pass
        cv.addSubview_(link)

        # descrizione breve (multi-riga)
        cv.addSubview_(self._about_label(
            APP_BLURB, NSMakeRect(24, AH - 410, AW - 48, 78), 11,
            NSColor.secondaryLabelColor()))

        # copyright in fondo
        cv.addSubview_(self._about_label(
            APP_COPYRIGHT, NSMakeRect(0, 18, AW, 16), 10,
            NSColor.tertiaryLabelColor()))

        self._aboutWindow = w
        w.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def windowWillClose_(self, notification):
        # rilascia il riferimento quando l'utente chiude l'About
        if (getattr(self, "_aboutWindow", None) is not None and
                notification.object() is self._aboutWindow):
            self._aboutWindow = None

    # -- costruzione della finestra e dell'interfaccia ----------------------
    @objc.python_method
    def _build_window(self):
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        rect = NSMakeRect(0, 0, WIN_W, WIN_H)
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False)
        self.window.setTitle_("FormulaDeck — Editor di formule LaTeX")
        if self.window.respondsToSelector_("setSubtitle:"):
            self.window.setSubtitle_("di " + APP_AUTHOR)
        self.window.setMinSize_(NSMakeSize(760, 520))
        self.window.center()

        content = self.window.contentView()

        # ----- BARRA AZIONI (in alto, larghezza flessibile) -----------------
        toolbar = NSView.alloc().initWithFrame_(
            NSMakeRect(0, WIN_H - TOOLBAR_H, WIN_W, TOOLBAR_H))
        toolbar.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        content.addSubview_(toolbar)

        x = 12
        x = self._add_toolbar_button(toolbar, x, "Inline  $…$", "wrapInline:")
        x = self._add_toolbar_button(toolbar, x, "Display  $$…$$", "wrapDisplay:")
        x = self._add_toolbar_button(toolbar, x, "Copia LaTeX", "copyLatex:")
        x = self._add_toolbar_button(toolbar, x, "Importa…", "importLatex:")
        x = self._add_toolbar_button(toolbar, x, "Pulisci", "clearText:")

        # contatore caratteri (a destra)
        self.charLabel = NSTextField.alloc().initWithFrame_(
            NSMakeRect(WIN_W - 130, (TOOLBAR_H - 18) / 2, 118, 18))
        self.charLabel.setBezeled_(False)
        self.charLabel.setEditable_(False)
        self.charLabel.setSelectable_(False)
        self.charLabel.setDrawsBackground_(False)
        self.charLabel.setAlignment_(2)  # right
        self.charLabel.setTextColor_(NSColor.secondaryLabelColor())
        self.charLabel.setFont_(NSFont.systemFontOfSize_(11))
        self.charLabel.setStringValue_("0 caratteri")
        # ancoraggio a destra: margine sinistro flessibile + top fisso
        self.charLabel.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        toolbar.addSubview_(self.charLabel)

        body_h = WIN_H - TOOLBAR_H

        # ----- SIDEBAR (sinistra, altezza flessibile) -----------------------
        sidebar = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, SIDEBAR_W, body_h))
        sidebar.setAutoresizingMask_(NSViewHeightSizable | NSViewMaxXMargin)
        content.addSubview_(sidebar)

        # selettore di categoria
        self.catPopup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(12, body_h - 40, SIDEBAR_W - 24, 26), False)
        for name in core.PALETTES.keys():
            self.catPopup.addItemWithTitle_(name)
        self.catPopup.setTarget_(self)
        self.catPopup.setAction_("categoryChanged:")
        self.catPopup.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        sidebar.addSubview_(self.catPopup)

        # griglia simboli scrollabile
        self.gridScroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(8, 8, SIDEBAR_W - 16, body_h - 56))
        self.gridScroll.setHasVerticalScroller_(True)
        self.gridScroll.setBorderType_(NSBezelBorder)
        self.gridScroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        sidebar.addSubview_(self.gridScroll)

        # ----- AREA DESTRA: split verticale (sorgente sopra, preview sotto) --
        right = NSSplitView.alloc().initWithFrame_(
            NSMakeRect(SIDEBAR_W, 0, WIN_W - SIDEBAR_W, body_h))
        right.setVertical_(False)        # divisione orizzontale -> panes impilati
        right.setDividerStyle_(2)        # thin
        right.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        content.addSubview_(right)

        rw = WIN_W - SIDEBAR_W

        # sorgente LaTeX (NSTextView in NSScrollView)
        srcScroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, body_h * 0.55, rw, body_h * 0.45))
        srcScroll.setHasVerticalScroller_(True)
        srcScroll.setBorderType_(NSBezelBorder)
        self.textView = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, rw, body_h * 0.45))
        self.textView.setFont_(NSFont.userFixedPitchFontOfSize_(15))
        self.textView.setRichText_(False)
        self.textView.setAutomaticQuoteSubstitutionEnabled_(False)
        self.textView.setAutomaticDashSubstitutionEnabled_(False)
        self.textView.setAutomaticTextReplacementEnabled_(False)
        self.textView.setAllowsUndo_(True)
        self.textView.setDelegate_(self)
        self.textView.setTextContainerInset_(NSMakeSize(8, 8))
        srcScroll.setDocumentView_(self.textView)

        # preview KaTeX (WKWebView)
        cfg = WKWebViewConfiguration.alloc().init()
        self.webView = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(0, 0, rw, body_h * 0.55), cfg)
        self.webView.setNavigationDelegate_(self)

        right.addSubview_(srcScroll)        # pane superiore (sorgente)
        right.addSubview_(self.webView)     # pane inferiore (anteprima)

        self.window.makeKeyAndOrderFront_(None)
        self.window.makeFirstResponder_(self.textView)

    @objc.python_method
    def _add_toolbar_button(self, parent, x, title, action):
        w = max(96, 11 * len(title))
        btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(x, (TOOLBAR_H - 30) / 2, w, 30))
        btn.setTitle_(title)
        btn.setBezelStyle_(NSBezelStyleRounded)
        btn.setTarget_(self)
        btn.setAction_(action)
        btn.setAutoresizingMask_(NSViewMaxXMargin | NSViewMinYMargin)
        parent.addSubview_(btn)
        return x + w + 8

    # -- griglia dei simboli -------------------------------------------------
    @objc.python_method
    def _populate_grid(self, category):
        items = core.PALETTES[category]["items"]
        self._templates = [it["insert"] for it in items]

        rows = (len(items) + GRID_COLS - 1) // GRID_COLS
        cell_w = BTN_W + GRID_GAP
        cell_h = BTN_H + GRID_GAP
        width = self.gridScroll.contentSize().width
        height = max(self.gridScroll.contentSize().height,
                     GRID_PAD * 2 + rows * cell_h)

        grid = FlippedView.alloc().initWithFrame_(
            NSMakeRect(0, 0, width, height))

        # centratura orizzontale della griglia nel viewport
        total_w = GRID_COLS * BTN_W + (GRID_COLS - 1) * GRID_GAP
        x0 = max(GRID_PAD, (width - total_w) / 2)

        for idx, it in enumerate(items):
            r = idx // GRID_COLS
            c = idx % GRID_COLS
            bx = x0 + c * cell_w
            by = GRID_PAD + r * cell_h
            btn = NSButton.alloc().initWithFrame_(
                NSMakeRect(bx, by, BTN_W, BTN_H))
            btn.setTitle_(it["glyph"])
            btn.setBezelStyle_(NSBezelStyleRegularSquare)
            btn.setFont_(NSFont.systemFontOfSize_(15))
            btn.setToolTip_(it["tip"])
            btn.setTag_(idx)
            btn.setTarget_(self)
            btn.setAction_("symbolClicked:")
            grid.addSubview_(btn)

        self.gridScroll.setDocumentView_(grid)
        # porta lo scroll in cima
        grid.scrollPoint_((0, 0))

    # -- azioni Cocoa (selettori reali, terminano con '_') ------------------
    def categoryChanged_(self, sender):
        self._populate_grid(sender.titleOfSelectedItem())

    def symbolClicked_(self, sender):
        insert = self._templates[sender.tag()]
        text, caret = core.expand_template(insert)
        rng = self.textView.selectedRange()
        ts = self.textView.textStorage()
        ts.replaceCharactersInRange_withString_(rng, text)
        new_loc = rng.location + caret
        self.textView.setSelectedRange_(NSMakeRange(new_loc, 0))
        self._update_outputs()
        self.window.makeFirstResponder_(self.textView)

    def wrapInline_(self, sender):
        s = core.wrap_inline(self._current_latex())
        self._copy_to_pasteboard(s)

    def wrapDisplay_(self, sender):
        s = core.wrap_display(self._current_latex())
        self._copy_to_pasteboard(s)

    def copyLatex_(self, sender):
        self._copy_to_pasteboard(self._current_latex())

    def clearText_(self, sender):
        self.textView.textStorage().replaceCharactersInRange_withString_(
            NSMakeRange(0, len(self._current_latex())), "")
        self._update_outputs()
        self.window.makeFirstResponder_(self.textView)

    def importLatex_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Importa LaTeX")
        alert.setInformativeText_(
            "Incolla l'espressione: i delimitatori $…$, $$…$$, \\[…\\], "
            "\\(…\\) vengono rimossi automaticamente.")
        alert.addButtonWithTitle_("Importa")
        alert.addButtonWithTitle_("Annulla")

        field_scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(0, 0, 360, 90))
        field_scroll.setHasVerticalScroller_(True)
        field_scroll.setBorderType_(NSBezelBorder)
        tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 360, 90))
        tv.setFont_(NSFont.userFixedPitchFontOfSize_(13))
        tv.setRichText_(False)
        field_scroll.setDocumentView_(tv)
        alert.setAccessoryView_(field_scroll)

        if alert.runModal() == 1000:  # primo bottone (Importa)
            raw = tv.string()
            clean = core.sanitize_import(raw)
            self.textView.textStorage().replaceCharactersInRange_withString_(
                NSMakeRange(0, len(self._current_latex())), clean)
            self._update_outputs()
        self.window.makeFirstResponder_(self.textView)

    # -- delegato NSTextView -------------------------------------------------
    def textDidChange_(self, notification):
        self._update_outputs()

    # -- delegato WKNavigation ----------------------------------------------
    def webView_didFinishNavigation_(self, webView, navigation):
        self._web_ready = True
        self._render_preview()

    # -- metodi di servizio (Python puro) -----------------------------------
    @objc.python_method
    def _current_latex(self):
        return self.textView.string()

    @objc.python_method
    def _update_outputs(self):
        latex = self._current_latex()
        n = len(latex)
        self.charLabel.setStringValue_(
            "%d carattere" % n if n == 1 else "%d caratteri" % n)
        self._render_preview()

    @objc.python_method
    def _render_preview(self):
        if not self._web_ready:
            return
        js = core.build_render_js(self._current_latex())
        self.webView.evaluateJavaScript_completionHandler_(js, None)

    @objc.python_method
    def _load_preview(self):
        index = resource_path("preview", "index.html")
        file_url = NSURL.fileURLWithPath_(index)
        dir_url = NSURL.fileURLWithPath_(os.path.dirname(index))
        self.webView.loadFileURL_allowingReadAccessToURL_(file_url, dir_url)

    @objc.python_method
    def _copy_to_pasteboard(self, s):
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(s, NSPasteboardTypeString)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
