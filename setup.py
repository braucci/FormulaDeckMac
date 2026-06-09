# -*- coding: utf-8 -*-
"""
setup.py — Configurazione py2app per FormulaDeck.

Build di distribuzione (standalone, NON alias):
    python setup.py py2app

Lo script build.sh automatizza venv + dipendenze + pulizia + questa build.
"""

from setuptools import setup

APP = ["app.py"]

# La cartella `preview` (index.html + vendor/katex con css, js e font) viene
# copiata integralmente in Contents/Resources: così la preview KaTeX funziona
# OFFLINE, senza alcuna dipendenza di rete a runtime.
DATA_FILES = ["preview"]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/icon.icns",
    # Moduli che py2app deve includere esplicitamente nel grafo delle dipendenze.
    "includes": ["objc", "Cocoa", "Foundation", "WebKit", "core"],
    "plist": {
        "CFBundleName": "FormulaDeck",
        "CFBundleDisplayName": "FormulaDeck",
        "CFBundleIdentifier": "io.github.braucci.formuladeck",
        "CFBundleVersion": "1.1.0",
        "CFBundleShortVersionString": "1.1.0",
        "LSMinimumSystemVersion": "11.0",
        # Abilita l'adattamento nativo a Dark Mode.
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "© 2025 Biagio Raucci — Licenza MIT",
        "CFBundleDocumentTypes": [],
    },
}

setup(
    app=APP,
    name="FormulaDeck",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
