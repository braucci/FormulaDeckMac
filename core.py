# -*- coding: utf-8 -*-
"""
core.py — Motore di dominio di FormulaDeck.

Questo modulo NON dipende da AppKit/PyObjC: è logica pura, testabile in
isolamento anche su Linux. La separazione rispetto a `app.py` (la GUI Cocoa)
è la stessa che in un codice CFD separa il *solutore* dal *post-processore*:
qui la "soluzione" è la stringa LaTeX, mentre la preview renderizzata è solo
post-processing visuale di quella soluzione.

Responsabilità del modulo:
  1. PALETTES  : catalogo dei simboli (dati di dominio, nessuna UI).
  2. expand_template(): converte un template (con segnaposto in stile MathLive
     #0 / #? / #@) in LaTeX "piatto" pronto per un editor testuale, calcolando
     l'offset di cursore in cui l'utente dovrebbe iniziare a digitare.
  3. wrap_inline / wrap_display : delimitatori $…$ e $$…$$.
  4. sanitize_import() : rimozione robusta dei delimitatori in import.
  5. build_render_js() : produce la chiamata JavaScript per renderizzare la
     formula nella WKWebView via KaTeX (escaping affidato a json.dumps).
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# 1. CATALOGO DEI SIMBOLI (dati di dominio)
#    Ogni voce: tip (tooltip), label, glyph (etichetta del bottone), insert
#    (template LaTeX con segnaposto). I segnaposto #0/#?/#@ sono ereditati
#    dalla convenzione MathLive dell'app web originale: vengono normalizzati
#    da expand_template().
# ---------------------------------------------------------------------------

PALETTES: "OrderedDict[str, Dict]" = OrderedDict([
    ("Algebra", {
        "icon": "a/b",
        "items": [
            {"tip": "Frazione",          "label": "Frazione",           "glyph": "a⁄b",  "insert": r"\frac{#0}{#?}"},
            {"tip": "Radice quadrata",   "label": "Radice quadrata",    "glyph": "√x",   "insert": r"\sqrt{#0}"},
            {"tip": "Radice n-esima",    "label": "Radice n-esima",     "glyph": "ⁿ√x",  "insert": r"\sqrt[#?]{#0}"},
            {"tip": "Potenza",           "label": "Potenza",            "glyph": "xⁿ",   "insert": r"#@^{#?}"},
            {"tip": "Pedice",            "label": "Pedice",             "glyph": "xᵢ",   "insert": r"#@_{#?}"},
            {"tip": "Apice e pedice",    "label": "Apice + pedice",     "glyph": "xᵢⁿ",  "insert": r"#@_{#?}^{#?}"},
            {"tip": "Parentesi tonde",   "label": "Parentesi tonde",    "glyph": "( )",  "insert": r"(#0)"},
            {"tip": "Parentesi quadre",  "label": "Parentesi quadre",   "glyph": "[ ]",  "insert": r"[#0]"},
            {"tip": "Parentesi graffe",  "label": "Parentesi graffe",   "glyph": "{ }",  "insert": r"\{#0\}"},
            {"tip": "Valore assoluto",   "label": "Valore assoluto",    "glyph": "|x|",  "insert": r"\left|#0\right|"},
            {"tip": "Norma",             "label": "Norma",              "glyph": "‖x‖",  "insert": r"\left\|#0\right\|"},
            {"tip": "Fattoriale",        "label": "Fattoriale",         "glyph": "n!",   "insert": r"n!"},
            {"tip": "Binomiale",         "label": "Coefficiente binom.", "glyph": "(ⁿₖ)", "insert": r"\binom{#0}{#?}"},
            {"tip": "Diverso",           "label": "Diverso da",         "glyph": "≠",    "insert": r"\neq"},
            {"tip": "Circa uguale",      "label": "Circa uguale",       "glyph": "≈",    "insert": r"\approx"},
            {"tip": "Identico",          "label": "Identico a",         "glyph": "≡",    "insert": r"\equiv"},
            {"tip": "Minore o uguale",   "label": "Minore o uguale",    "glyph": "≤",    "insert": r"\leq"},
            {"tip": "Maggiore o uguale", "label": "Maggiore o uguale",  "glyph": "≥",    "insert": r"\geq"},
            {"tip": "Più o meno",        "label": "Più o meno",         "glyph": "±",    "insert": r"\pm"},
            {"tip": "Moltiplicazione",   "label": "Moltiplicazione",    "glyph": "×",    "insert": r"\times"},
            {"tip": "Divisione",         "label": "Divisione",          "glyph": "÷",    "insert": r"\div"},
            {"tip": "Prodotto puntato",  "label": "Prodotto puntato",   "glyph": "·",    "insert": r"\cdot"},
            {"tip": "Infinito",          "label": "Infinito",           "glyph": "∞",    "insert": r"\infty"},
        ],
    }),
    ("Calcolo", {
        "icon": "∫",
        "items": [
            {"tip": "Limite",            "label": "Limite",                "glyph": "lim",     "insert": r"\lim_{#0\to #?}"},
            {"tip": "Derivata",          "label": "Derivata ordinaria",    "glyph": "dy⁄dx",   "insert": r"\frac{d#0}{d#?}"},
            {"tip": "Derivata parziale", "label": "Derivata parziale",     "glyph": "∂y⁄∂x",   "insert": r"\frac{\partial #0}{\partial #?}"},
            {"tip": "Derivata seconda",  "label": "Derivata seconda",      "glyph": "d²y⁄dx²", "insert": r"\frac{d^{2}#0}{d#?^{2}}"},
            {"tip": "Integrale",         "label": "Integrale indefinito",  "glyph": "∫",       "insert": r"\int #0\,d#?"},
            {"tip": "Integrale definito", "label": "Integrale definito",   "glyph": "∫ₐᵇ",     "insert": r"\int_{#0}^{#?} #?\,d#?"},
            {"tip": "Doppio integrale",  "label": "Integrale doppio",      "glyph": "∬",       "insert": r"\iint"},
            {"tip": "Triplo integrale",  "label": "Integrale triplo",      "glyph": "∭",       "insert": r"\iiint"},
            {"tip": "Integrale circuit.", "label": "Integrale circuitale", "glyph": "∮",       "insert": r"\oint"},
            {"tip": "Sommatoria",        "label": "Sommatoria",            "glyph": "Σ",       "insert": r"\sum"},
            {"tip": "Σ con limiti",      "label": "Sommatoria con indici", "glyph": "Σⁿᵢ",     "insert": r"\sum_{#0=#?}^{#?}"},
            {"tip": "Produttoria",       "label": "Produttoria",           "glyph": "∏",       "insert": r"\prod_{#0=#?}^{#?}"},
            {"tip": "Nabla",             "label": "Nabla / gradiente",     "glyph": "∇",       "insert": r"\nabla"},
            {"tip": "Differenziale",     "label": "Differenziale",         "glyph": "d",       "insert": r"d"},
            {"tip": "Parziale",          "label": "Simbolo ∂",             "glyph": "∂",       "insert": r"\partial"},
            {"tip": "Tende a",           "label": "Tende a (→)",           "glyph": "→",       "insert": r"\to"},
            {"tip": "Implica",           "label": "Implica (⇒)",           "glyph": "⇒",       "insert": r"\Rightarrow"},
            {"tip": "Se e solo se",      "label": "Se e solo se (⇔)",      "glyph": "⇔",       "insert": r"\Leftrightarrow"},
        ],
    }),
    ("Greche", {
        "icon": "α",
        "items": [
            {"tip": "alpha",   "label": "alpha",   "glyph": "α", "insert": r"\alpha"},
            {"tip": "beta",    "label": "beta",    "glyph": "β", "insert": r"\beta"},
            {"tip": "gamma",   "label": "gamma",   "glyph": "γ", "insert": r"\gamma"},
            {"tip": "delta",   "label": "delta",   "glyph": "δ", "insert": r"\delta"},
            {"tip": "epsilon", "label": "epsilon", "glyph": "ε", "insert": r"\epsilon"},
            {"tip": "zeta",    "label": "zeta",    "glyph": "ζ", "insert": r"\zeta"},
            {"tip": "eta",     "label": "eta",     "glyph": "η", "insert": r"\eta"},
            {"tip": "theta",   "label": "theta",   "glyph": "θ", "insert": r"\theta"},
            {"tip": "iota",    "label": "iota",    "glyph": "ι", "insert": r"\iota"},
            {"tip": "kappa",   "label": "kappa",   "glyph": "κ", "insert": r"\kappa"},
            {"tip": "lambda",  "label": "lambda",  "glyph": "λ", "insert": r"\lambda"},
            {"tip": "mu",      "label": "mu",      "glyph": "μ", "insert": r"\mu"},
            {"tip": "nu",      "label": "nu",      "glyph": "ν", "insert": r"\nu"},
            {"tip": "xi",      "label": "xi",      "glyph": "ξ", "insert": r"\xi"},
            {"tip": "pi",      "label": "pi",      "glyph": "π", "insert": r"\pi"},
            {"tip": "rho",     "label": "rho",     "glyph": "ρ", "insert": r"\rho"},
            {"tip": "sigma",   "label": "sigma",   "glyph": "σ", "insert": r"\sigma"},
            {"tip": "tau",     "label": "tau",     "glyph": "τ", "insert": r"\tau"},
            {"tip": "phi",     "label": "phi",     "glyph": "φ", "insert": r"\phi"},
            {"tip": "chi",     "label": "chi",     "glyph": "χ", "insert": r"\chi"},
            {"tip": "psi",     "label": "psi",     "glyph": "ψ", "insert": r"\psi"},
            {"tip": "omega",   "label": "omega",   "glyph": "ω", "insert": r"\omega"},
            {"tip": "Gamma",   "label": "Gamma",   "glyph": "Γ", "insert": r"\Gamma"},
            {"tip": "Delta",   "label": "Delta",   "glyph": "Δ", "insert": r"\Delta"},
            {"tip": "Theta",   "label": "Theta",   "glyph": "Θ", "insert": r"\Theta"},
            {"tip": "Lambda",  "label": "Lambda",  "glyph": "Λ", "insert": r"\Lambda"},
            {"tip": "Xi",      "label": "Xi",      "glyph": "Ξ", "insert": r"\Xi"},
            {"tip": "Pi",      "label": "Pi",      "glyph": "Π", "insert": r"\Pi"},
            {"tip": "Sigma",   "label": "Sigma",   "glyph": "Σ", "insert": r"\Sigma"},
            {"tip": "Phi",     "label": "Phi",     "glyph": "Φ", "insert": r"\Phi"},
            {"tip": "Psi",     "label": "Psi",     "glyph": "Ψ", "insert": r"\Psi"},
            {"tip": "Omega",   "label": "Omega",   "glyph": "Ω", "insert": r"\Omega"},
        ],
    }),
    ("Logica & Insiemi", {
        "icon": "∈",
        "items": [
            {"tip": "Per ogni",       "label": "Per ogni",         "glyph": "∀", "insert": r"\forall"},
            {"tip": "Esiste",         "label": "Esiste",           "glyph": "∃", "insert": r"\exists"},
            {"tip": "Non esiste",     "label": "Non esiste",       "glyph": "∄", "insert": r"\nexists"},
            {"tip": "Appartiene",     "label": "Appartiene a",     "glyph": "∈", "insert": r"\in"},
            {"tip": "Non appart.",    "label": "Non appartiene",   "glyph": "∉", "insert": r"\notin"},
            {"tip": "Sottoinsieme",   "label": "Sottoinsieme",     "glyph": "⊂", "insert": r"\subset"},
            {"tip": "Sottoins. ⊆",    "label": "Sottoinsieme ⊆",   "glyph": "⊆", "insert": r"\subseteq"},
            {"tip": "Sovrainsieme",   "label": "Sovrainsieme",     "glyph": "⊃", "insert": r"\supset"},
            {"tip": "Unione",         "label": "Unione",           "glyph": "∪", "insert": r"\cup"},
            {"tip": "Intersezione",   "label": "Intersezione",     "glyph": "∩", "insert": r"\cap"},
            {"tip": "Insieme vuoto",  "label": "Insieme vuoto",    "glyph": "∅", "insert": r"\emptyset"},
            {"tip": "Naturali",       "label": "Numeri naturali",  "glyph": "ℕ", "insert": r"\mathbb{N}"},
            {"tip": "Interi",         "label": "Numeri interi",    "glyph": "ℤ", "insert": r"\mathbb{Z}"},
            {"tip": "Razionali",      "label": "Numeri razionali", "glyph": "ℚ", "insert": r"\mathbb{Q}"},
            {"tip": "Reali",          "label": "Numeri reali",     "glyph": "ℝ", "insert": r"\mathbb{R}"},
            {"tip": "Complessi",      "label": "Numeri complessi", "glyph": "ℂ", "insert": r"\mathbb{C}"},
            {"tip": "AND",            "label": "AND logico",       "glyph": "∧", "insert": r"\land"},
            {"tip": "OR",             "label": "OR logico",        "glyph": "∨", "insert": r"\lor"},
            {"tip": "NOT",            "label": "NOT logico",       "glyph": "¬", "insert": r"\neg"},
            {"tip": "Therefore",      "label": "Quindi (∴)",       "glyph": "∴", "insert": r"\therefore"},
            {"tip": "Because",        "label": "Poiché (∵)",       "glyph": "∵", "insert": r"\because"},
        ],
    }),
    ("Matrici", {
        "icon": "[a]",
        "items": [
            {"tip": "Matrice 2×2 ( )",  "label": "Matrice 2×2 ( )",   "glyph": "(2×2)", "insert": r"\begin{pmatrix}#0 & #? \\ #? & #? \end{pmatrix}"},
            {"tip": "Matrice 3×3 ( )",  "label": "Matrice 3×3 ( )",   "glyph": "(3×3)", "insert": r"\begin{pmatrix}#0 & #? & #? \\ #? & #? & #? \\ #? & #? & #? \end{pmatrix}"},
            {"tip": "Matrice 2×2 [ ]",  "label": "Matrice 2×2 [ ]",   "glyph": "[2×2]", "insert": r"\begin{bmatrix}#0 & #? \\ #? & #? \end{bmatrix}"},
            {"tip": "Matrice 3×3 [ ]",  "label": "Matrice 3×3 [ ]",   "glyph": "[3×3]", "insert": r"\begin{bmatrix}#0 & #? & #? \\ #? & #? & #? \\ #? & #? & #? \end{bmatrix}"},
            {"tip": "Determinante 2×2", "label": "Determinante 2×2",  "glyph": "|2×2|", "insert": r"\begin{vmatrix}#0 & #? \\ #? & #? \end{vmatrix}"},
            {"tip": "Determinante 3×3", "label": "Determinante 3×3",  "glyph": "|3×3|", "insert": r"\begin{vmatrix}#0 & #? & #? \\ #? & #? & #? \\ #? & #? & #? \end{vmatrix}"},
            {"tip": "Sistema 2 eq.",    "label": "Sistema 2 equazioni", "glyph": "{2eq", "insert": r"\begin{cases}#0 \\ #? \end{cases}"},
            {"tip": "Sistema 3 eq.",    "label": "Sistema 3 equazioni", "glyph": "{3eq", "insert": r"\begin{cases}#0 \\ #? \\ #? \end{cases}"},
            {"tip": "Vettore colonna 3", "label": "Vettore colonna",  "glyph": "(v↓)", "insert": r"\begin{pmatrix}#0 \\ #? \\ #? \end{pmatrix}"},
            {"tip": "Vettore riga 3",   "label": "Vettore riga",      "glyph": "(v→)", "insert": r"\begin{pmatrix}#0 & #? & #? \end{pmatrix}"},
            {"tip": "Vettore (freccia)", "label": "Vettore con freccia", "glyph": "v⃗", "insert": r"\vec{#0}"},
            {"tip": "Overrightarrow",   "label": "Vettore AB",        "glyph": "AB⃗", "insert": r"\overrightarrow{#0}"},
            {"tip": "Trasposta",        "label": "Trasposta",         "glyph": "Aᵀ",  "insert": r"#@^{T}"},
            {"tip": "Inversa",          "label": "Inversa",           "glyph": "A⁻¹", "insert": r"#@^{-1}"},
            {"tip": "Punti orizz.",     "label": "Puntini orizzont.", "glyph": "⋯",   "insert": r"\cdots"},
            {"tip": "Punti vert.",      "label": "Puntini verticali", "glyph": "⋮",   "insert": r"\vdots"},
            {"tip": "Punti diag.",      "label": "Puntini diagonali", "glyph": "⋱",   "insert": r"\ddots"},
        ],
    }),
    ("Funzioni", {
        "icon": "ƒ",
        "items": [
            {"tip": "seno",          "label": "Seno",            "glyph": "sin",    "insert": r"\sin"},
            {"tip": "coseno",        "label": "Coseno",          "glyph": "cos",    "insert": r"\cos"},
            {"tip": "tangente",      "label": "Tangente",        "glyph": "tan",    "insert": r"\tan"},
            {"tip": "cotangente",    "label": "Cotangente",      "glyph": "cot",    "insert": r"\cot"},
            {"tip": "arcoseno",      "label": "Arcoseno",        "glyph": "arcsin", "insert": r"\arcsin"},
            {"tip": "arcocoseno",    "label": "Arcocoseno",      "glyph": "arccos", "insert": r"\arccos"},
            {"tip": "arcotangente",  "label": "Arcotangente",    "glyph": "arctan", "insert": r"\arctan"},
            {"tip": "seno iperb.",   "label": "Seno iperbol.",   "glyph": "sinh",   "insert": r"\sinh"},
            {"tip": "coseno iperb.", "label": "Coseno iperbol.", "glyph": "cosh",   "insert": r"\cosh"},
            {"tip": "Log naturale",  "label": "Logaritmo nat.",  "glyph": "ln",     "insert": r"\ln"},
            {"tip": "Logaritmo",     "label": "Logaritmo",       "glyph": "log",    "insert": r"\log"},
            {"tip": "Log in base b", "label": "Log in base b",   "glyph": "logᵦ",   "insert": r"\log_{#0}"},
            {"tip": "Esponenziale",  "label": "Esponenziale",    "glyph": "eˣ",     "insert": r"e^{#0}"},
            {"tip": "Massimo",       "label": "Massimo",         "glyph": "max",    "insert": r"\max"},
            {"tip": "Minimo",        "label": "Minimo",          "glyph": "min",    "insert": r"\min"},
            {"tip": "Estremo sup.",  "label": "Estremo superiore", "glyph": "sup",  "insert": r"\sup"},
            {"tip": "Estremo inf.",  "label": "Estremo inferiore", "glyph": "inf",  "insert": r"\inf"},
            {"tip": "Argomento",     "label": "Argomento",       "glyph": "arg",    "insert": r"\arg"},
            {"tip": "M.C.D.",        "label": "M.C.D.",          "glyph": "gcd",    "insert": r"\gcd"},
        ],
    }),
    ("Frecce & Accenti", {
        "icon": "→",
        "items": [
            {"tip": "Freccia destra",   "label": "Freccia destra",     "glyph": "→",  "insert": r"\rightarrow"},
            {"tip": "Freccia sinistra", "label": "Freccia sinistra",   "glyph": "←",  "insert": r"\leftarrow"},
            {"tip": "Freccia su",       "label": "Freccia su",         "glyph": "↑",  "insert": r"\uparrow"},
            {"tip": "Freccia giù",      "label": "Freccia giù",        "glyph": "↓",  "insert": r"\downarrow"},
            {"tip": "Doppia destra",    "label": "Doppia destra",      "glyph": "⇒",  "insert": r"\Rightarrow"},
            {"tip": "Doppia sinistra",  "label": "Doppia sinistra",    "glyph": "⇐",  "insert": r"\Leftarrow"},
            {"tip": "Mappa in",         "label": "Mappa in",           "glyph": "↦",  "insert": r"\mapsto"},
            {"tip": "Lunga destra",     "label": "Lunga destra",       "glyph": "⟶",  "insert": r"\longrightarrow"},
            {"tip": "Cappello",         "label": "Cappello (hat)",     "glyph": "x̂",  "insert": r"\hat{#0}"},
            {"tip": "Tilde",            "label": "Tilde",              "glyph": "x̃",  "insert": r"\tilde{#0}"},
            {"tip": "Bar",              "label": "Barra (bar)",        "glyph": "x̄",  "insert": r"\bar{#0}"},
            {"tip": "Overline",         "label": "Sopralinea",         "glyph": "x̅",  "insert": r"\overline{#0}"},
            {"tip": "Underline",        "label": "Sottolinea",         "glyph": "x̲",  "insert": r"\underline{#0}"},
            {"tip": "Punto sopra",      "label": "Punto sopra",        "glyph": "ẋ",  "insert": r"\dot{#0}"},
            {"tip": "Due punti sopra",  "label": "Due punti sopra",    "glyph": "ẍ",  "insert": r"\ddot{#0}"},
            {"tip": "Vettore",          "label": "Vettore",            "glyph": "v⃗", "insert": r"\vec{#0}"},
            {"tip": "Overrightarrow",   "label": "Sopralinea + freccia", "glyph": "AB⃗", "insert": r"\overrightarrow{#0}"},
        ],
    }),
])


# ---------------------------------------------------------------------------
# 2. ESPANSIONE DEI TEMPLATE
# ---------------------------------------------------------------------------

# I template contengono i segnaposto MathLive:
#   #0  -> slot primario (dove l'utente inizia a scrivere)
#   #?  -> slot secondario
#   #@  -> "corpo implicito": in un editor WYSIWYG racchiude la selezione;
#          in un editor testuale lineare non ha contenuto, perché l'apice o il
#          pedice si lega al token che precede il cursore.
#
# Strategia di normalizzazione (dimostrata corretta nei test del modulo):
# i template includono già le parentesi graffe strutturali (es. \frac{#0}{#?}),
# quindi è sufficiente RIMUOVERE i segnaposto (sostituirli con stringa vuota)
# per ottenere LaTeX sintatticamente valido e pulito (-> \frac{}{}). L'offset
# di cursore restituito è la posizione del primo #0 (o, in mancanza, del primo
# #?); così dopo l'inserimento il cursore si trova già nello slot principale.

def expand_template(insert: str) -> Tuple[str, int]:
    """Converte un template con segnaposto in LaTeX piatto.

    Ritorna (testo, caret_offset).
    """
    out: List[str] = []
    length = 0
    caret = None       # posizione del primo #0
    fallback = None    # posizione del primo #?
    i = 0
    n = len(insert)
    while i < n:
        if insert[i] == "#" and i + 1 < n and insert[i + 1] in "0?@":
            tok = insert[i + 1]
            if tok == "0" and caret is None:
                caret = length
            elif tok == "?" and fallback is None:
                fallback = length
            # tutti e tre i segnaposto non emettono caratteri
            i += 2
            continue
        out.append(insert[i])
        length += 1
        i += 1
    text = "".join(out)
    if caret is None:
        caret = fallback if fallback is not None else len(text)
    return text, caret


# ---------------------------------------------------------------------------
# 3. DELIMITATORI INLINE / DISPLAY
# ---------------------------------------------------------------------------

def wrap_inline(latex: str) -> str:
    """Avvolge in modalità inline: $…$ (formula nel flusso del testo)."""
    return "$" + latex + "$"


def wrap_display(latex: str) -> str:
    """Avvolge in modalità display: $$…$$ (formula centrata, fuori flusso)."""
    return "$$" + latex + "$$"


# ---------------------------------------------------------------------------
# 4. IMPORT: rimozione robusta dei delimitatori
# ---------------------------------------------------------------------------

_DELIMS = [
    (re.compile(r"^\$\$([\s\S]*)\$\$$"), r"\1"),    # $$ … $$
    (re.compile(r"^\$([\s\S]*)\$$"),     r"\1"),    # $ … $
    (re.compile(r"^\\\[([\s\S]*)\\\]$"), r"\1"),    # \[ … \]
    (re.compile(r"^\\\(([\s\S]*)\\\)$"), r"\1"),    # \( … \)
]


def sanitize_import(text: str) -> str:
    """Rimuove i delimitatori esterni più comuni e ripulisce gli spazi."""
    s = (text or "").strip()
    for pattern, repl in _DELIMS:
        m = pattern.match(s)
        if m:
            s = pattern.sub(repl, s).strip()
            break
    return s


# ---------------------------------------------------------------------------
# 5. PONTE VERSO LA PREVIEW (WKWebView + KaTeX)
# ---------------------------------------------------------------------------

def build_render_js(latex: str) -> str:
    """Genera la chiamata JavaScript per renderizzare `latex` nella WKWebView.

    L'escaping è delegato a json.dumps(): produce un literal JS valido e sicuro
    anche in presenza di backslash, apici e Unicode, eliminando ogni rischio di
    injection o di rottura della stringa (principio: una sola fonte di verità
    per l'escaping, mai concatenazioni a mano).
    """
    payload = json.dumps(latex if latex and latex.strip() else "")
    return "renderLatex(" + payload + ");"


# ---------------------------------------------------------------------------
# TEST DI COERENZA (documentazione eseguibile).
# Eseguibili anche su Linux:  python3 core.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # --- expand_template: identità note --------------------------------------
    t, c = expand_template(r"\frac{#0}{#?}")
    assert t == r"\frac{}{}", t
    assert t[c:c + 1] == "}" or c == 6, (t, c)   # cursore tra le prime graffe
    assert c == 6, c

    t, c = expand_template(r"(#0)")
    assert t == "()" and c == 1, (t, c)

    t, c = expand_template(r"#@^{#?}")
    assert t == "^{}" and c == 2, (t, c)         # apice vuoto, cursore interno

    t, c = expand_template(r"\sqrt[#?]{#0}")
    assert t == r"\sqrt[]{}", t
    # preferenza per #0 (radicando) rispetto a #? (indice)
    assert t[c - 1] == "{", (t, c)

    t, c = expand_template(r"\sum")
    assert t == r"\sum" and c == len(t), (t, c)

    t, c = expand_template(r"\begin{pmatrix}#0 & #? \\ #? & #? \end{pmatrix}")
    assert "#0" not in t and "#?" not in t, t
    assert r"\\" in t, t                          # il ritorno a capo LaTeX resta

    # --- delimitatori --------------------------------------------------------
    assert wrap_inline("x") == "$x$"
    assert wrap_display("x") == "$$x$$"

    # --- sanitize_import -----------------------------------------------------
    assert sanitize_import("$$E=mc^2$$") == "E=mc^2"
    assert sanitize_import("$x$") == "x"
    assert sanitize_import(r"\[y\]") == "y"
    assert sanitize_import(r"\(z\)") == "z"
    assert sanitize_import("   a+b   ") == "a+b"

    # --- build_render_js: escaping sicuro ------------------------------------
    js = build_render_js(r"\frac{1}{2}")
    assert js.startswith("renderLatex(") and js.endswith(");"), js
    assert r"\\frac" in js, js                    # backslash correttamente escapato
    assert build_render_js("") == 'renderLatex("");'

    # --- integrità del catalogo ----------------------------------------------
    n_items = 0
    for cat, payload in PALETTES.items():
        assert "icon" in payload and "items" in payload, cat
        for it in payload["items"]:
            for k in ("tip", "label", "glyph", "insert"):
                assert k in it and isinstance(it[k], str), (cat, it)
            # ogni insert deve espandersi senza lasciare segnaposto residui
            txt, _ = expand_template(it["insert"])
            assert "#0" not in txt and "#?" not in txt and "#@" not in txt, (cat, it["insert"])
            n_items += 1

    print("OK — tutti i test superati.")
    print("Categorie: %d   Simboli totali: %d" % (len(PALETTES), n_items))
