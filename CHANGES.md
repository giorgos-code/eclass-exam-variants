# Αλλαγές: PDF Exam Groups Generator

## Τι υλοποιήθηκε

Νέο εργαλείο που επιτρέπει στον καθηγητή να επιλέγει ερωτήσεις από την τράπεζα ερωτήσεων και να παράγει αυτόματα **N ισοδύναμα τεστ σε ZIP** (ένα PDF ανά ομάδα: Α, Β, Γ…) με τυχαία σειρά ερωτήσεων και επιλογών.

---

## Αρχεία που δημιουργήθηκαν

### `modules/exercise/pdf_exam_groups.php` (ΝΕΟΣ)

**Τι κάνει:** Κεντρικός controller για τη δημιουργία εξεταστικών ομάδων.

Λειτουργεί σε δύο φάσεις:

**GET — Φόρμα επιλογής:**
- Φίλτρα: ανά exercise, κατηγορία, δυσκολία
- Λίστα ερωτήσεων με checkboxes (+ κουμπιά Επέλεξε Όλες / Καμία)
- Παράμετροι: τίτλος εξέτασης, ημερομηνία, διάρκεια, αριθμός ομάδων (1–26), ερωτήσεις ανά ομάδα
- Live counter επιλεγμένων ερωτήσεων με προειδοποίηση αν δεν φτάνουν

**POST — Παραγωγή ZIP:**
1. Validation: αν επιλεγμένες < ερωτήσεις/ομάδα → μήνυμα λάθους
2. Για κάθε ομάδα i (Α, Β, Γ…):
   - `shuffle()` των επιλεγμένων ερωτήσεων → πάρε τις M πρώτες
   - Κάθε ομάδα κάνει **ανεξάρτητο** shuffle, οπότε ακόμα και αν N×M > total, η σειρά είναι πάντα διαφορετική
3. Κάθε ομάδα → ξεχωριστό PDF μέσω **mPDF** (ίδια βιβλιοθήκη με το υπάρχον `export.php`)
4. Όλα τα PDFs → **ZipArchive** → download ως `[τίτλος] - Εξεταστικές Ομάδες.zip`

**Γιατί ZIP αντί για ένα PDF:**
Ο καθηγητής μπορεί να εκτυπώσει/στείλει κάθε ομάδα ξεχωριστά χωρίς να χρειαστεί να "κόψει" ένα μεγάλο PDF.

**Γιατί ανεξάρτητο shuffle ανά ομάδα (και όχι partition):**
Ακόμα κι αν δεν υπάρχουν αρκετές ερωτήσεις για εντελώς διαφορετικά σετ, κάθε ομάδα έχει διαφορετική σειρά — αρκεί για αντι-αντιγραφή. Αν υπάρχουν αρκετές (N×M ≤ total), φυσικά παίρνουν διαφορετικές.

**Νέες functions στο αρχείο:**

| Function | Τι κάνει |
|---|---|
| `build_exam_html()` | Παράγει το HTML ενός τεστ (header + ερωτήσεις) για το mPDF |
| `exam_question_html()` | Εμφανίζει τις επιλογές **χωρίς** να δείχνει ποια είναι σωστή, κάνει shuffle τις επιλογές |

**Γιατί νέα `exam_question_html()` αντί για reuse της `question_html()` από `export.php`:**
Η `question_html()` είναι για τον καθηγητή (εμφανίζει σωστές απαντήσεις, βαθμούς, σχόλια). Η `exam_question_html()` είναι για τον φοιτητή (μόνο επιλογές, shuffled, χωρίς indication του σωστού).

**Υποστηριζόμενοι τύποι ερωτήσεων:**

| Τύπος | Εμφάνιση στο PDF |
|---|---|
| UNIQUE_ANSWER | Κύκλοι (○) ανακατεμένοι |
| MULTIPLE_ANSWER | Τετράγωνα (□) ανακατεμένα |
| TRUE_FALSE | Κύκλοι (○) |
| FREE_TEXT | 5 κενές γραμμές |
| FILL_IN_BLANKS / TOLERANT | Κείμενο με \_\_\_\_\_ |
| FILL_IN_FROM_PREDEFINED | Κείμενο με \_\_\_ + επιλογές (shuffled) |
| MATCHING | Πίνακας: αριστερά → δεξιά (δεξιά shuffled) |
| ORAL | Παραλείπεται |

---

## Αρχεία που τροποποιήθηκαν

### `modules/exercise/question_pool.php`

**Τι άλλαξε:** Προστέθηκε νέο κουμπί στο `action_bar` δίπλα στο υπάρχον «Εξαγωγή σε PDF».

**Γραμμή:** Μετά το `$langDumpPDF` entry στον πίνακα `$action_bar_options` (~γραμμή 267).

```php
[ 'title' => $langCreateExamGroups,
  'url'   => "pdf_exam_groups.php?course=$course_code",
  'icon'  => 'fa-file-zipper',
  'button-class' => 'btn-success' ],
```

**Γιατί εδώ:** Ο καθηγητής βρίσκεται ήδη στην τράπεζα ερωτήσεων — είναι το πιο φυσικό σημείο εισόδου. Δεν απαιτείται να έχει φτιάξει exercise εκ των προτέρων.

---

### `lang/el/messages.inc.php`

**Τι άλλαξε:** Προστέθηκαν 22 νέα strings μετά τη γραμμή `$langDumpPDF`.

**Γιατί στο `messages.inc.php` και όχι στο `common.inc.php`:** Τα exercise-related strings βρίσκονται ήδη στο `messages.inc.php` (π.χ. `$langDumpPDF`, `$langQuestionPool`, `$langQuesList`). Ακολουθούμε την ίδια σύμβαση.

Νέα strings:
```
$langCreateExamGroups, $langExamTitle, $langExamDate, $langExamDuration,
$langNumGroups, $langNumGroupsInfo, $langQuestionsPerGroup, $langGroupLabel,
$langExamGroups, $langGenerateExamZIP, $langExamParameters, $langSelectQuestions,
$langExamGroupsInfo, $langNotEnoughQuestions, $langNotEnoughQuestionsJS,
$langQuestionsSelected, $langNeedAtLeast, $langSelectAtLeastOne,
$langPoints, $langAllCategories, $langNoQuestionsFound
```

---

### `lang/en/messages.inc.php`

**Τι άλλαξε:** Τα ίδια 22 strings σε αγγλική απόδοση, στην ίδια σχετική θέση.

---

## Αρχεία που ΔΕΝ άλλαξαν

| Αρχείο | Γιατί δεν χρειάστηκε αλλαγή |
|---|---|
| `exercise.class.php` | Δεν αγγίζουμε τη λογική exercises |
| `question.class.php` | Χρησιμοποιούμε ήδη τις υπάρχουσες read() methods |
| `answer.class.php` | Χρησιμοποιούμε ήδη τις υπάρχουσες methods |
| `export.php` | Δεν τον τροποποιούμε — αντίθετα φτιάξαμε παράλληλη λειτουργία |
| **Βάση Δεδομένων** | **Καμία αλλαγή** — όλη η λογική είναι in-memory |

---

## Ροή χρήσης

```
Τράπεζα Ερωτήσεων (question_pool.php)
    └── κουμπί "Δημιουργία Εξεταστικών Ομάδων PDF"
            └── pdf_exam_groups.php (GET)
                    ├── Φίλτρα (exercise / κατηγορία / δυσκολία)
                    ├── Checkboxes ερωτήσεων
                    └── Παράμετροι (τίτλος, ημ/νία, Ν ομάδες, Μ ερωτήσεις)
                            └── [Δημιουργία ZIP] → POST
                                    └── shuffle × N → N PDFs → ZIP download
```
