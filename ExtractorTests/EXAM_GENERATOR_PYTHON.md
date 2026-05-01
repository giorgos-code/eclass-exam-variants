# Εξεταστικές Ομάδες PDF — Python Standalone Generator

Standalone Python εργαλείο που συνδέεται στη βάση δεδομένων του eClass και παράγει αυτόματα **N ισοδύναμα εξεταστικά τεστ σε ZIP** (ένα PDF ανά ομάδα: Α, Β, Γ…), με τυχαία σειρά ερωτήσεων και επιλογών.

---

## Αρχεία

| Αρχείο | Περιγραφή |
|---|---|
| `exam_generator.py` | Το κύριο script (Flask web app + PDF generator) |
| `exam_generator_requirements.txt` | Λίστα Python dependencies |

---

## Εγκατάσταση σε οποιοδήποτε μηχάνημα

### Προαπαιτούμενα

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **MySQL** να τρέχει (XAMPP, WAMP, Docker, ή οποιοσδήποτε MySQL server)
- **Πρόσβαση στη βάση δεδομένων του eClass**

### Βήμα 1 — Αντέγραψε τα αρχεία

Χρειάζεσαι μόνο **δύο αρχεία** από το eClass directory:

```
exam_generator.py
exam_generator_requirements.txt
```

Και τον φάκελο με τα ελληνικά fonts (για σωστή εμφάνιση στο PDF):

```
template/modern/fonts/open-sans-v13-greek_cyrillic_latin_greek-ext-regular.ttf
template/modern/fonts/open-sans-v13-greek_cyrillic_latin_greek-ext-700.ttf
```

> Αν δεν έχεις τα fonts, το script τρέχει κανονικά αλλά τα ελληνικά στο PDF δεν θα εμφανίζονται σωστά (fallback σε Helvetica).

### Βήμα 2 — Εγκατάσταση dependencies

```bash
pip install -r exam_generator_requirements.txt
```

Ή χειροκίνητα:

```bash
pip install flask mysql-connector-python fpdf2 phpserialize
```

> `phpserialize` είναι **προαιρετικό** — χρειάζεται μόνο για ερωτήσεις τύπου *Επιλογή από Λίστα (FILL_IN_FROM_PREDEFINED)*. Χωρίς αυτό, αυτές οι ερωτήσεις εμφανίζονται απλοποιημένες.

### Βήμα 3 — Ρύθμιση σύνδεσης βάσης

Άνοιξε το `exam_generator.py` και άλλαξε τις πρώτες γραμμές ρυθμίσεων:

```python
DB_HOST     = 'localhost'    # ή η IP του MySQL server
DB_USER     = 'root'         # χρήστης MySQL
DB_PASSWORD = ''             # κωδικός (κενό αν δεν έχει)
DB_NAME     = 'eclass'       # όνομα βάσης — έλεγξε στο phpMyAdmin
DB_PORT     = 3306           # default port
APP_PORT    = 5000           # port του web interface
```

**Πώς βρίσκεις το όνομα της βάσης:**
- Άνοιξε phpMyAdmin (`http://localhost/phpmyadmin`)
- Βρες ποια βάση περιέχει τον πίνακα `exercise_question`
- Αυτό είναι το `DB_NAME`

### Βήμα 4 — Εκτέλεση

```bash
python exam_generator.py
```

Άνοιξε τον browser στο:

```
http://localhost:5000
```

---

## Τι εμφανίζει το terminal κατά την εκκίνηση

```
=======================================================
  Εξεταστικές Ομάδες PDF Generator
=======================================================
  Βάση δεδομένων : root@localhost/eclass
  Fonts          : OK
  phpserialize   : OK
  URL            : http://localhost:5000
=======================================================
```

Αν τα fonts δεν βρεθούν ή το phpserialize δεν είναι εγκατεστημένο, εμφανίζεται προειδοποίηση αλλά το script τρέχει κανονικά.

---

## Ανάλυση Κώδικα

### 1. Ρυθμίσεις και Σταθερές

```python
# ── Σύνδεση βάσης ──────────────────────────────────
DB_HOST     = 'localhost'
DB_USER     = 'root'
DB_PASSWORD = ''
DB_NAME     = 'eclass'

# ── Ελληνικά fonts (από τον φάκελο template του eClass) ──
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR    = os.path.join(SCRIPT_DIR, 'template', 'modern', 'fonts')
FONT_REGULAR = os.path.join(FONTS_DIR, 'open-sans-v13-...-regular.ttf')
FONT_BOLD    = os.path.join(FONTS_DIR, 'open-sans-v13-...-700.ttf')
```

`SCRIPT_DIR` υπολογίζεται αυτόματα — το script βρίσκει τα fonts **σχετικά με τη θέση του**, οπότε λειτουργεί σε οποιοδήποτε μηχάνημα χωρίς αλλαγές path.

---

### 2. Σταθερές Τύπων Ερωτήσεων

```python
UNIQUE_ANSWER           = 1   # Μοναδική επιλογή (radio)
MULTIPLE_ANSWER         = 2   # Πολλαπλή επιλογή (checkbox)
FILL_IN_BLANKS          = 3   # Συμπλήρωση κενών
MATCHING                = 4   # Αντιστοίχηση
TRUE_FALSE              = 5   # Σωστό / Λάθος
FREE_TEXT               = 6   # Ελεύθερο κείμενο
FILL_IN_BLANKS_TOLERANT = 7   # Συμπλήρωση κενών (ανεκτικό)
FILL_IN_FROM_PREDEFINED = 8   # Επιλογή από προκαθορισμένη λίστα
ORAL                    = 13  # Προφορική (παραλείπεται)
```

Οι ίδιες ακριβώς τιμές με το `include/constants.php` του eClass.

---

### 3. Βάση Δεδομένων — Batch Queries

```python
def db_query(sql, params=()):
    conn = get_db()
    cur  = conn.cursor(dictionary=True)  # επιστρέφει dicts αντί για tuples
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows
```

Για να αποφύγουμε το **N+1 query problem** (ξεχωριστό query για κάθε ερώτηση × κάθε ομάδα), χρησιμοποιούμε bulk helpers που φέρνουν όλα τα δεδομένα σε **2 queries** πριν ξεκινήσει η παραγωγή:

```python
def get_questions_by_ids(question_ids):
    placeholders = ','.join(['%s'] * len(question_ids))
    rows = db_query(
        f"SELECT id, question, type, weight FROM exercise_question "
        f"WHERE id IN ({placeholders})",
        tuple(question_ids))
    return {r['id']: r for r in rows}   # dict με key=id για O(1) lookup

def get_answers_bulk(question_ids):
    placeholders = ','.join(['%s'] * len(question_ids))
    rows = db_query(
        f"SELECT question_id, answer, correct, r_position, weight "
        f"FROM exercise_answer WHERE question_id IN ({placeholders}) "
        f"ORDER BY question_id, r_position",
        tuple(question_ids))
    result = {}
    for r in rows:
        result.setdefault(r['question_id'], []).append(r)
    return result   # dict: question_id → [answers]
```

**Γιατί έχει σημασία:** Με 5 ομάδες × 10 ερωτήσεις, χωρίς batch θα γίνονταν 100 queries. Με batch γίνονται πάντα 2.

---

### 4. Βοηθητικές Συναρτήσεις Κειμένου

```python
def strip_html(text):
    text = re.sub(r'<br\s*/?>', '\n', str(text), flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    return html_lib.unescape(text).strip()

def _blanks(text):
    return re.sub(r'\[[^\]]+\]', '_______', strip_html(text))
```

- `strip_html` — αφαιρεί HTML tags που αποθηκεύει το eClass στις ερωτήσεις, αντικαθιστά `<br>` με νέα γραμμή.
- `_blanks` — χρησιμοποιείται για fill-in-blanks: αντικαθιστά `[σωστή_απάντηση]` με `_______` ώστε ο φοιτητής να μη βλέπει την απάντηση.

---

### 5. Κλάση PDF — `ExamPDF`

Κληρονομεί από `FPDF` και φτιάχνει ένα A4 PDF για μία ομάδα.

```python
class ExamPDF(FPDF):
    def __init__(self, course_name, exam_title, group_label, exam_date, duration):
        super().__init__(orientation='P', unit='mm', format='A4')
        # ...
        if os.path.exists(FONT_REGULAR) and os.path.exists(FONT_BOLD):
            self.add_font('Main', '',  FONT_REGULAR)
            self.add_font('Main', 'B', FONT_BOLD)
            self.f = 'Main'        # Open Sans με υποστήριξη ελληνικών
        else:
            self.f = 'Helvetica'   # fallback χωρίς ελληνικά
```

#### Header κάθε PDF

```python
def _draw_header(self):
    # Τίτλος μαθήματος + τίτλος εξέτασης (centered)
    # Badge "ΟΜΑΔΑ Α" με πλαίσιο (πάνω δεξιά)
    # Ημερομηνία + διάρκεια (πάνω αριστερά)
    # Πλαίσιο φοιτητή: Ονοματεπώνυμο / Α.Μ. / Τμήμα
    # Οριζόντια γραμμή διαχωρισμού
```

#### Προσθήκη Ερώτησης

```python
def add_question(self, num, q_text, q_type, answers, weight=0):
    # Εκτυπώνει: "1.  Κείμενο ερώτησης  (2.0 μ.)"
    # Μετά καλεί τον κατάλληλο renderer ανάλογα με τον τύπο
```

---

### 6. Renderers ανά Τύπο Ερώτησης

#### Μοναδική / Πολλαπλή Επιλογή

```python
def _render_choices(self, answers, q_type):
    shuffled = answers[:]
    random.shuffle(shuffled)        # ανακάτεμα επιλογών
    marker = '○  ' if q_type == UNIQUE_ANSWER else '□  '
    for ans in shuffled:
        self.multi_cell(..., f'{marker}{strip_html(ans["answer"])}')
```

Κάθε φορά που παράγεται PDF για νέα ομάδα, το `shuffle` δίνει **διαφορετική σειρά επιλογών**.

#### Σωστό / Λάθος

```python
def _render_true_false(self):
    self.cell(..., '○  Σωστό          ○  Λάθος')
```

#### Ελεύθερο Κείμενο

```python
def _render_free_text(self):
    for _ in range(5):   # 5 κενές γραμμές για απάντηση
        self.line(...)
        self.ln(10)
```

#### Συμπλήρωση Κενών

```python
def _render_fill_blanks(self, answers):
    # answers[0]['answer'] περιέχει: "Η πρωτεύουσα της Γαλλίας είναι [Παρίσι]."
    self.multi_cell(..., _blanks(answers[0].get('answer', '')))
    # Εμφανίζει: "Η πρωτεύουσα της Γαλλίας είναι _______."
```

#### Αντιστοίχηση (Matching)

```python
def _render_matching(self, answers):
    by_pos = {int(a['r_position']): a for a in answers}

    # Στο eClass: αριστερά στοιχεία έχουν correct != 0
    # correct = r_position του αντίστοιχου δεξιού στοιχείου
    left_pairs = []
    for a in answers:
        correct_pos = int(a.get('correct') or 0)
        if correct_pos and correct_pos in by_pos:
            left_pairs.append((strip_html(a['answer']),
                               strip_html(by_pos[correct_pos]['answer'])))

    right_col = [r for _, r in left_pairs]
    random.shuffle(right_col)   # ανακάτεμα δεξιάς στήλης

    # Εμφάνιση: Α. [αριστερό]  →  1. [δεξί shuffled]
```

---

### 7. Αλγόριθμος Παραγωγής ZIP

```python
def build_zip(course_name, exam_title, exam_date, duration,
              num_groups, per_group, question_ids):

    # Βήμα 1: 2 queries για ΟΛΑ τα δεδομένα (ανεξάρτητα από αριθμό ομάδων)
    q_data   = get_questions_by_ids(question_ids)
    ans_data = get_answers_bulk(question_ids)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i in range(num_groups):
            group_label = chr(65 + i)   # 0→'A', 1→'B', 2→'C' ...

            # Βήμα 2: ανεξάρτητο shuffle για κάθε ομάδα
            pool = question_ids[:]
            random.shuffle(pool)
            group_ids = pool[:per_group]

            # Βήμα 3: παραγωγή PDF
            pdf = ExamPDF(course_name, exam_title, group_label, exam_date, duration)
            for idx, qid in enumerate(group_ids):
                q = q_data.get(qid)
                pdf.add_question(idx + 1, q['question'], int(q['type']),
                                 ans_data.get(qid, []),
                                 round(float(q['weight'] or 0), 1))

            # Βήμα 4: προσθήκη PDF στο ZIP
            zf.writestr(f'{safe_filename(exam_title)} - OMADA {group_label}.pdf',
                        bytes(pdf.output()))
    buf.seek(0)
    return buf
```

**Γιατί ανεξάρτητο shuffle:** Ακόμα κι αν δεν υπάρχουν αρκετές ερωτήσεις για εντελώς διαφορετικά σετ, κάθε ομάδα έχει πάντα **διαφορετική σειρά** — αρκεί για αντι-αντιγραφή.

---

### 8. Flask Routes

```
GET  /                      → Αρχική σελίδα, επιλογή μαθήματος
GET  /course/<id>           → Φόρτωση ερωτήσεων για το μάθημα
GET  /course/<id>?exercise_id=X&category_id=Y&difficulty=Z
                            → Ίδιο με φίλτρα
POST /generate              → Παράγει και κατεβάζει το ZIP
```

---

## Ροή Χρήσης

```
http://localhost:5000
    │
    ▼
Επιλογή Μαθήματος [dropdown]
    │
    ▼
Φίλτρα (Exercise / Κατηγορία / Δυσκολία)  ← προαιρετικά
    │
    ▼
Πίνακας ερωτήσεων με checkboxes
    │  + Παράμετροι: Τίτλος / Ημερομηνία / Διάρκεια
    │               Αριθμός Ομάδων / Ερωτήσεις ανά Ομάδα
    │
    ▼  [Δημιουργία ZIP με PDF]
    │
    ▼
Browser κατεβάζει: "Τίτλος - Exetastikes Omades.zip"
    ├── Τίτλος - OMADA A.pdf
    ├── Τίτλος - OMADA B.pdf
    └── Τίτλος - OMADA C.pdf
```

---

## Υποστηριζόμενοι Τύποι Ερωτήσεων

| Τύπος | Εμφάνιση στο PDF |
|---|---|
| Μοναδική Επιλογή | ○ επιλογές (shuffled) |
| Πολλαπλή Επιλογή | □ επιλογές (shuffled) |
| Σωστό/Λάθος | ○ Σωστό  ○ Λάθος |
| Ελεύθερο Κείμενο | 5 κενές γραμμές |
| Συμπλήρωση Κενών | Κείμενο με _______ |
| Αντιστοίχηση | Πίνακας Α→Β (Β shuffled) |
| Επιλογή από Λίστα | Κείμενο + λέξεις bank |
| Προφορική | Παραλείπεται |

---

## Αντιμετώπιση Προβλημάτων

### `ModuleNotFoundError`
```bash
pip install flask mysql-connector-python fpdf2
```

### `Can't connect to MySQL server`
- Βεβαιώσου ότι ο MySQL server τρέχει
- Έλεγξε `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` στο αρχείο

### Τα ελληνικά δεν εμφανίζονται στο PDF
Βεβαιώσου ότι τα αρχεία font υπάρχουν:
```
template/modern/fonts/open-sans-v13-greek_cyrillic_latin_greek-ext-regular.ttf
template/modern/fonts/open-sans-v13-greek_cyrillic_latin_greek-ext-700.ttf
```
Αν λείπουν, αντέγραψέ τα από το eClass directory.

### Port 5000 είναι κατειλημμένο
Άλλαξε στο αρχείο:
```python
APP_PORT = 5001   # ή οποιοδήποτε άλλο port
```

### Η βάση δεδομένων δεν έχει ερωτήσεις
Το εργαλείο διαβάζει από τον πίνακα `exercise_question`. Βεβαιώσου ότι το eClass έχει ερωτήσεις καταχωρημένες για το μάθημα που επιλέγεις.
