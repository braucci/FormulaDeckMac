# FormulaDeck

Editor nativo di formule LaTeX per macOS: comporre espressioni matematiche da una tavolozza di simboli, vederne l'anteprima renderizzata in tempo reale e copiarne il sorgente LaTeX (grezzo, inline `$…$` o display `$$…$$`).

![macOS](https://img.shields.io/badge/macOS-11%2B-black?logo=apple)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

Autore: **B. Raucci** — [www.raucci.net](https://www.raucci.net)
La voce di menu *FormulaDeck → Informazioni su FormulaDeck* apre la scheda con autore, versione e collegamento al sito.

**Novità 1.1.0** — la tavolozza dei simboli è ora ridimensionabile (divisore trascinabile) e la griglia è *responsiva*: numero di colonne e larghezza dei pulsanti si adattano alla larghezza disponibile, così nessun simbolo viene mai tagliato.

---

## Architettura

```
FormulaDeck/
├── core.py            # logica di dominio pura: catalogo simboli, espansione
│                      # dei template, sanitizzazione import, generazione JS.
│                      # NESSUNA dipendenza da AppKit -> testabile su Linux.
├── app.py             # GUI Cocoa/AppKit (PyObjC): finestra, tavolozza,
│                      # NSTextView sorgente, anteprima WKWebView, azioni.
├── setup.py           # configurazione py2app
├── build.sh           # build automatizzata (venv + KaTeX + py2app standalone)
├── requirements.txt   # pyobjc-core, Cocoa, WebKit, py2app
├── README.md
├── LICENSE            # MIT
├── .gitignore         # esclude build/, dist/, .venv/, preview/vendor/
├── preview/
│   ├── index.html     # pagina dell'anteprima; espone renderLatex()
│   └── vendor/katex/  # KaTeX (css + js + font) impacchettato in fase di build
└── assets/
    ├── icon.svg       # sorgente vettoriale master (1024×1024)
    ├── icon.icns      # icona compilata, riferita da setup.py
    ├── icon.png       # rasterizzazione master
    └── icon.iconset/  # 10 PNG canoniche Apple (16…512@2x)
```

Il progetto applica una **separazione netta tra logica di dominio e presentazione**, la stessa che in un codice CFD distingue il *solutore* dal *post-processore*:

- **`core.py` è il solutore.** Riceve "condizioni al contorno" (il template scelto sulla tavolozza) e produce la "soluzione": la stringa LaTeX. Non sa nulla di finestre, bottoni o pixel ed è verificabile in isolamento — proprio come si valida un solutore numerico confrontandolo con soluzioni analitiche note prima di accoppiarlo a qualsiasi grafica.
- **`app.py` è il post-processore.** L'unica "fonte di verità" è la sorgente LaTeX contenuta nella `NSTextView`; l'anteprima KaTeX, il conteggio dei caratteri e le copie inline/display sono tutte *derivazioni* di quella sorgente, esattamente come i campi di pressione e le linee di corrente sono derivazioni del campo di velocità calcolato dal solutore.

Questa scelta non è estetica: rende `core.py` riusabile (anche fuori da macOS), testabile senza avviare l'interfaccia, e isola i guasti — un errore di rendering nell'anteprima non può corrompere la sorgente.

> **Nota sul WYSIWYG.** L'app web di partenza usa MathLive, un editor matematico *what-you-see-is-what-you-get*. Replicarlo in puro AppKit equivarrebbe a riscrivere MathLive: fuori scope. La versione nativa adotta quindi un modello più rigoroso e robusto — **la sorgente LaTeX è il modello, l'anteprima è la sua visualizzazione** — e affida il rendering a WebKit (framework nativo di macOS) con KaTeX, perché non esiste un renderer LaTeX nativo di sistema. È la stessa logica per cui non si reinventa un mesher quando ne esiste uno affidabile: si sceglie lo strumento giusto per il sotto-problema.

---

## Il modello logico

Il cuore di `core.py` è la **normalizzazione di un template** in LaTeX pronto all'inserimento.

Sia `T` una stringa sull'alfabeto dei caratteri LaTeX a cui si aggiungono tre **segnaposto** ereditati dalla convenzione MathLive:

- `#0` — slot primario (dove il cursore deve fermarsi dopo l'inserimento);
- `#?` — slot secondario;
- `#@` — *corpo implicito*: in un editor WYSIWYG racchiude la selezione corrente; in un editor testuale lineare non ha contenuto, perché apice e pedice si legano al token che precede il cursore.

La funzione `expand_template` calcola la coppia

```
N(T) = (T', k)
```

dove `T'` è ottenuta **rimuovendo** tutti i segnaposto e `k` è l'offset di cursore, definito come la posizione del primo `#0` (o, in sua assenza, del primo `#?`; altrimenti la fine di `T'`).

**Perché la semplice rimozione produce LaTeX valido.** I template sono progettati con le parentesi graffe *strutturali* già presenti attorno ai segnaposto. Ad esempio:

```
T  = \frac{#0}{#?}
T' = \frac{}{}          (sintatticamente ben formato)
k  = 6                  (cursore tra le prime graffe)
```

Rimuovere il segnaposto è concettualmente analogo all'**adimensionalizzazione**: si toglie la grandezza "di riempimento" lasciando intatta la forma canonica della struttura. La correttezza di questa proprietà non è asserita per fede ma **verificata** dal blocco di test di `core.py`, che controlla, per tutti i 147 simboli del catalogo, che `T'` non contenga segnaposto residui e che le identità note siano rispettate (`(#0)` → `()`, `#@^{#?}` → `^{}`, ecc.).

Le altre regole del modello:

| Operazione | Regola |
|---|---|
| Inline | `wrap_inline(L) = $L$` |
| Display | `wrap_display(L) = $$L$$` |
| Import | rimozione dei delimitatori esterni `$…$`, `$$…$$`, `\[…\]`, `\(…\)` |
| Rendering | `build_render_js(L)` → chiamata JS `renderLatex(<L codificato>)` |

L'escaping della stringa verso JavaScript è delegato interamente a `json.dumps`: una **sola fonte di verità** per l'escaping elimina alla radice i rischi di stringa malformata o di injection, lo stesso principio per cui in un solutore si centralizza la definizione delle costanti fisiche invece di ricopiarle in ogni routine.

---

## Requisiti

- **macOS 11 (Big Sur) o successivo** — supporto nativo a Dark Mode.
- **Python 3.9+** (consigliato il Python di [python.org](https://www.python.org) o via Homebrew).
- Connessione di rete **solo in fase di build** (per scaricare KaTeX); a runtime l'app è completamente offline.

---

## Esecuzione in sviluppo

```bash
# 1. clona il repository
git clone https://github.com/braucci/FormulaDeck.git
cd FormulaDeck

# 2. ambiente virtuale
python3 -m venv .venv
source .venv/bin/activate

# 3. dipendenze
pip install -r requirements.txt

# 4. KaTeX per l'anteprima (se preview/vendor/katex non è già presente)
#    Il modo più semplice è lanciare build.sh una volta, oppure scaricarlo a mano:
mkdir -p preview/vendor/katex/fonts
curl -sL https://registry.npmjs.org/katex/-/katex-0.17.0.tgz | tar -xz -C /tmp
cp /tmp/package/dist/katex.min.css preview/vendor/katex/
cp /tmp/package/dist/katex.min.js  preview/vendor/katex/
cp /tmp/package/dist/fonts/*.woff2 preview/vendor/katex/fonts/

# 5. avvio
python3 app.py
```

---

## Creazione del bundle `.app`

```bash
./build.sh
```

Lo script crea un virtualenv pulito, installa le dipendenze, **impacchetta KaTeX** dentro `preview/vendor/katex`, cancella `build/` e `dist/` e lancia `python setup.py py2app` in **modalità standalone** (mai alias). Al termine:

```bash
# provare subito l'app
open dist/FormulaDeck.app

# installarla: trascinare il bundle in /Applications
```

### Diagnosi di un crash all'avvio

Il doppio clic nasconde i messaggi di errore. Per ottenere il **traceback Python** completo, avviare il binario interno direttamente da Terminale:

```bash
./dist/FormulaDeck.app/Contents/MacOS/FormulaDeck
```

---

## Test di coerenza

`core.py` contiene un blocco `if __name__ == "__main__"` con asserzioni che fungono sia da *sanity check* sia da documentazione eseguibile. Si lancia su qualunque sistema (anche Linux), senza GUI:

```bash
python3 core.py
# OK — tutti i test superati.
# Categorie: 7   Simboli totali: 147
```

I test verificano: la normalizzazione dei template su identità note, i delimitatori inline/display, la rimozione dei delimitatori in import, l'escaping JavaScript e l'integrità dell'intero catalogo dei simboli.

---

## Note sulla distribuzione

- **Gatekeeper.** L'app non è firmata con un Apple Developer ID. Alla prima apertura macOS la blocca: aprirla con **clic destro → Apri**, poi confermare. È sufficiente la prima volta.
- **Firma e notarizzazione** (Developer ID + `notarytool`) servirebbero per una distribuzione "pulita" a terzi senza l'avviso di Gatekeeper. Sono fuori dallo scope di questo progetto didattico.
- **Cache delle icone.** Se dopo una nuova build l'icona non si aggiorna nel Finder, è la cache di sistema: `killall Finder` (o logout/login) la rigenera.
- **iCloud + repository Git.** Evitare di tenere la cartella di lavoro dentro `~/Desktop` o `~/Documents` sincronizzati su iCloud Drive: la sincronizzazione può interferire con `dist/`, `.venv/` e i metadati Git. Lavorare in una cartella locale non sincronizzata.

---

## Licenza

Distribuito sotto licenza **MIT** (vedi `LICENSE`). Include KaTeX, anch'esso MIT.
