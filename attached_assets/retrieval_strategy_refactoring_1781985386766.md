# Refactoring della Strategia di Retrieval e Creazione Database

Questo documento illustra il cuore delle modifiche apportate alla logica di ricerca (retrieval) dell'engine musicale e spiega in dettaglio il processo di creazione e popolamento del database vettoriale (ChromaDB) tramite l'apposito script.

---

## 1. Il Cuore del Refactoring (Retrieval Strategy)

Le modifiche a `main.py` ed `embeddings.py` cambiano radicalmente l'approccio alla ricerca delle lyrics. Il cambiamento si può riassumere in questi punti chiave:

### A. Passaggio a una Query Puramente Visuale
L'engine non invia più alcun prompt testuale all'LLM di embedding insieme all'immagine. 
- **Prima**: si inviava un prompt predefinito insieme all'immagine (o ai frame del video) per condizionare l'embedding verso il contesto del mood.
- **Ora**: la query inviata a OpenRouter (modello *Llama Nemotron*) include **esclusivamente l'immagine**. Per i video, l'embedding finale è semplicemente la media (average) matematica dei vettori dei singoli frame. 

### B. Rimozione del Clustering Locale
- **Prima**: ChromaDB fungeva da raccoglitore "agnostico" al mood. L'engine doveva estrarre un set di risultati e, in memory (a runtime), ricalcolare la distanza del coseno tra ciascun candidato trovato e i 5 vettori di mood per decidere in che categoria inserirlo.
- **Ora**: questa logica computazionalmente onerosa a runtime è stata interamente eliminata. **Il mood è ora una proprietà intrinseca salvata nei metadati** di ciascuna porzione di testo su ChromaDB.

### C. Nuova Paginazione e Filtraggio a Runtime
Con il mood già disponibile nel database, il meccanismo di query è stato ottimizzato:
- **Numero di risultati**: Aumentati i risultati di default in un'unica chiamata da 25 a 50 (`CANDIDATE_K = 50`).
- **Filtri Mirati**: La query su ChromaDB include ora una clausola `where` per restringere i risultati alle sole stanze di testo (lyrics) la cui lunghezza rientra nei bin compresi tra 25 e 100 caratteri (tramite l'operatore `$in: ["25-50", "50-75", "75-100"]`).
- **Costruzione della Risposta**: I risultati vengono formattati in una risposta che offre la chiave `best` (l'ordinamento assoluto puro ritornato dalla distanza della query visiva nel DB) e **categorizzazioni dinamiche** sulla base dei mood che sono stati *effettivamente recuperati*, eliminando forzature o calcoli locali.

---

## 2. Come Viene Creato il Chroma DB

Lo script Python allegato mostra come l'architettura sia stata spostata verso la fase di **pre-calcolo (ingestion)**. Ecco i passaggi con cui i dati finiscono dentro la collection `song_lyrics_min` su ChromaDB:

### A. Estrazione e Pulizia (Sanitizzazione)
Il processo legge un file JSONL (`lyrics_dataset.jsonl`) enorme sequenzialmente. Per ogni traccia:
1. Si estraggono **genere musicale** e **lingua**.
2. Le lyrics vengono separate in singole "stanze" (dividendo il testo a ogni doppio a capo `\n\n`).
3. La funzione `clean_stanza` rimuove il testo tra parentesi (spesso usato per indicare le voci secondarie o le istruzioni come "[Chorus]") e normalizza gli spazi.
4. La funzione `is_too_repetitive` si assicura di scartare le strofe prive di valore semantico, valutando l'incidenza di onomatopee/vocalizzi (es. "oh", "yeah", "la") e penalizzando testi con vocabolario troppo ripetitivo.
5. Si assegna a ogni stanza sopravvissuta un bin di lunghezza (`get_length_bin`), che sarà poi usato per i filtri descritti sopra.

### B. Creazione delle "Ancore" dei Mood
All'inizio dello script, vengono calcolati gli **embeddings delle definizioni (keywords) di tutti i mood supportati**. Questi vettori formano un set di "ancore". Questo accade una sola volta all'avvio dello script di seed.

### C. Embedding Massivo
Tutte le stanze processate con successo vengono date in pasto al `SentenceTransformer` che genera i vettori ad alta densità per l'intero dataset, sfruttando i batch per saturare l'acceleratore hardware.

### D. Assegnazione del Mood (Il Nuovo Cuore Logico)
Il tassello fondamentale avviene prima dell'inserimento nel DB, all'interno della funzione `assign_mood`:
- Viene misurata la `cosine_similarity` tra l'embedding testuale della singola stanza e l'embedding di ciascuna "ancora" di mood.
- Interviene la funzione **`apply_affinity`**: il punteggio matematico grezzo viene modificato (ponderato) in base al genere musicale. Questo serve per mappare semanticamente il testo al genere musicale (es. una canzone Metal potrebbe ricevere un "boost" sul mood Energetic a parità di testo).
- Alla stanza viene definitivamente assegnato il `top_mood` calcolato.

### E. Inserimento in ChromaDB
Infine, le stanze vengono aggiunte al PersistentClient di ChromaDB in batch di 5000 elementi. Assieme all'ID e al Vettore (Embedding List), viene salvato il dizionario `metadatas` per ciascun chunk contenente:
- `genre`
- `language`
- `length_bin`
- **`mood`** (Il risultato del calcolo precedente)

Questo approccio alleggerisce in modo sostanziale l'engine in fase di API Call, poiché ogni matching semantico tra "testo della canzone" e "mood desiderato" è già pre-incapsulato nel database fin dal momento della sua creazione.
