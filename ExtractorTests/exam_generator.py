#!/usr/bin/env python3
"""
Εξεταστικές Ομάδες PDF — Standalone Generator
Διαβάζει ερωτήσεις από τη βάση δεδομένων του eClass και παράγει ZIP με PDF εξεταστικά.

Εγκατάσταση:
    pip install flask mysql-connector-python fpdf2

Προαιρετικά (για ερωτήσεις FILL_IN_FROM_PREDEFINED):
    pip install phpserialize

Εκτέλεση:
    python exam_generator.py
    Άνοιξε τον browser στο http://localhost:5000
"""

import io, os, random, re, zipfile
import html as html_lib
import mysql.connector
from fpdf import FPDF
from flask import (Flask, flash, redirect, render_template_string,
                   request, send_file, url_for)

try:
    import phpserialize
    HAS_PHPSERIALIZE = True
except ImportError:
    HAS_PHPSERIALIZE = False

# ═══════════════════════════════════════════════════════════════
#  ΡΥΘΜΙΣΕΙΣ  ← Άλλαξε εδώ αν χρειαστεί
# ═══════════════════════════════════════════════════════════════
DB_HOST     = 'localhost'
DB_USER     = 'root'
DB_PASSWORD = ''
DB_NAME     = 'eclass'   # έλεγξε το config/config.php του eClass
DB_PORT     = 3306
APP_PORT    = 5000

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR    = os.path.join(SCRIPT_DIR, 'template', 'modern', 'fonts')
FONT_REGULAR = os.path.join(FONTS_DIR, 'open-sans-v13-greek_cyrillic_latin_greek-ext-regular.ttf')
FONT_BOLD    = os.path.join(FONTS_DIR, 'open-sans-v13-greek_cyrillic_latin_greek-ext-700.ttf')

# ═══════════════════════════════════════════════════════════════
#  ΣΤΑΘΕΡΕΣ ΤΥΠΩΝ ΕΡΩΤΗΣΕΩΝ  (eClass include/constants.php)
# ═══════════════════════════════════════════════════════════════
UNIQUE_ANSWER           = 1
MULTIPLE_ANSWER         = 2
FILL_IN_BLANKS          = 3
MATCHING                = 4
TRUE_FALSE              = 5
FREE_TEXT               = 6
FILL_IN_BLANKS_TOLERANT = 7
FILL_IN_FROM_PREDEFINED = 8
ORAL                    = 13

QTYPE_LABELS = {
    UNIQUE_ANSWER:           'Μοναδική',
    MULTIPLE_ANSWER:         'Πολλαπλή',
    FILL_IN_BLANKS:          'Κενά',
    MATCHING:                'Αντιστοίχηση',
    TRUE_FALSE:              'Σ/Λ',
    FREE_TEXT:               'Ελεύθερο',
    FILL_IN_BLANKS_TOLERANT: 'Κενά (Τολ.)',
    FILL_IN_FROM_PREDEFINED: 'Λίστα',
    ORAL:                    'Προφορική',
}

# ═══════════════════════════════════════════════════════════════
#  ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ ΒΑΣΗΣ ΔΕΔΟΜΕΝΩΝ
# ═══════════════════════════════════════════════════════════════
def get_db():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset='utf8mb4'
    )

def db_query(sql, params=()):
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_courses():
    return db_query("SELECT id, code, title FROM course ORDER BY title")

def get_course(course_id):
    rows = db_query("SELECT id, code, title FROM course WHERE id = %s", (course_id,))
    return rows[0] if rows else None

def get_exercises(course_id):
    return db_query(
        "SELECT id, title FROM exercise WHERE course_id = %s ORDER BY title",
        (course_id,))

def get_categories(course_id):
    return db_query(
        "SELECT question_cat_id, question_cat_name "
        "FROM exercise_question_cats WHERE course_id = %s ORDER BY question_cat_name",
        (course_id,))

def get_questions(course_id, exercise_id=None, category_id=None, difficulty=None):
    where  = ["eq.course_id = %s", f"eq.type != {ORAL}"]
    params = [course_id]
    join   = ""

    if exercise_id:
        join = "JOIN exercise_with_questions ewq ON eq.id = ewq.question_id"
        where.append("ewq.exercise_id = %s")
        params.append(exercise_id)
    if category_id is not None and int(category_id) != -1:
        where.append("eq.category = %s")
        params.append(int(category_id))
    if difficulty is not None and int(difficulty) not in (-1, 0):
        where.append("eq.difficulty = %s")
        params.append(int(difficulty))

    order = "ewq.q_position" if exercise_id else "eq.id"
    sql = f"""
        SELECT eq.id, eq.question, eq.type, eq.difficulty, eq.category, eq.weight
        FROM exercise_question eq {join}
        WHERE {' AND '.join(where)}
        ORDER BY {order}
    """
    return db_query(sql, params)

def get_answers(question_id):
    return db_query(
        "SELECT answer, correct, r_position, weight "
        "FROM exercise_answer WHERE question_id = %s ORDER BY r_position",
        (question_id,))

def get_question(question_id):
    rows = db_query(
        "SELECT id, question, type, weight FROM exercise_question WHERE id = %s",
        (question_id,))
    return rows[0] if rows else None

def get_questions_by_ids(question_ids):
    if not question_ids:
        return {}
    placeholders = ','.join(['%s'] * len(question_ids))
    rows = db_query(
        f"SELECT id, question, type, weight FROM exercise_question "
        f"WHERE id IN ({placeholders})",
        tuple(question_ids))
    return {r['id']: r for r in rows}

def get_answers_bulk(question_ids):
    if not question_ids:
        return {}
    placeholders = ','.join(['%s'] * len(question_ids))
    rows = db_query(
        f"SELECT question_id, answer, correct, r_position, weight "
        f"FROM exercise_answer WHERE question_id IN ({placeholders}) "
        f"ORDER BY question_id, r_position",
        tuple(question_ids))
    result = {}
    for r in rows:
        result.setdefault(r['question_id'], []).append(r)
    return result

# ═══════════════════════════════════════════════════════════════
#  ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ ΚΕΙΜΕΝΟΥ
# ═══════════════════════════════════════════════════════════════
def strip_html(text):
    if not text:
        return ''
    text = re.sub(r'<br\s*/?>', '\n', str(text), flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    return html_lib.unescape(text).strip()

def _blanks(text):
    return re.sub(r'\[[^\]]+\]', '_______', strip_html(text))

def safe_filename(s):
    return re.sub(r'[\\/:*?"<>|]', '_', str(s)).strip()

# ═══════════════════════════════════════════════════════════════
#  ΚΛΑΣΗ PDF
# ═══════════════════════════════════════════════════════════════
class ExamPDF(FPDF):

    def __init__(self, course_name, exam_title, group_label, exam_date, duration):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.course_name = course_name
        self.exam_title  = exam_title
        self.group_label = group_label
        self.exam_date   = exam_date
        self.duration    = duration

        self.set_margins(20, 20, 20)
        self.set_auto_page_break(auto=True, margin=20)

        if os.path.exists(FONT_REGULAR) and os.path.exists(FONT_BOLD):
            self.add_font('Main', '',  FONT_REGULAR)
            self.add_font('Main', 'B', FONT_BOLD)
            self.f = 'Main'
        else:
            self.f = 'Helvetica'
            print(f'[WARN] Τα Greek fonts δεν βρέθηκαν στο: {FONTS_DIR}')
            print('       Τα ελληνικά ενδέχεται να μην εμφανιστούν σωστά.')

        self.add_page()
        self._draw_header()

    def _draw_header(self):
        f, w = self.f, self.epw

        # Τίτλος μαθήματος
        self.set_font(f, 'B', 13)
        self.cell(w, 8, self.course_name, align='C', new_x='LMARGIN', new_y='NEXT')

        # Τίτλος εξέτασης
        self.set_font(f, '', 11)
        self.cell(w, 7, self.exam_title, align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(3)

        # Badge ομάδας (δεξιά) + μεταδεδομένα (αριστερά)
        y0      = self.get_y()
        badge_w = 58
        badge_h = 22
        badge_x = self.w - self.r_margin - badge_w

        self.set_draw_color(0)
        self.set_line_width(1.0)
        self.rect(badge_x, y0, badge_w, badge_h)
        self.set_font(f, 'B', 20)
        self.set_xy(badge_x, y0 + 1)
        self.cell(badge_w, badge_h - 2, f'ΟΜΑΔΑ {self.group_label}', align='C')

        self.set_xy(self.l_margin, y0)
        self.set_font(f, '', 10)
        self.set_line_width(0.3)
        meta_w = w - badge_w - 6
        if self.exam_date:
            self.cell(meta_w, 7, f'Ημερομηνία: {self.exam_date}',
                      new_x='LMARGIN', new_y='NEXT')
        if self.duration:
            self.cell(meta_w, 7, f'Διάρκεια: {self.duration} λεπτά',
                      new_x='LMARGIN', new_y='NEXT')

        self.set_y(max(self.get_y(), y0 + badge_h + 3))

        # Πλαίσιο φοιτητή
        info_y = self.get_y()
        self.rect(self.l_margin, info_y, w, 16)
        self.set_xy(self.l_margin + 3, info_y + 4)
        self.cell(w * 0.52, 6, 'Ονοματεπώνυμο: _________________________________')
        self.cell(w * 0.24, 6, 'Α.Μ.: __________')
        self.cell(w * 0.24, 6, 'Τμήμα: ________', new_x='LMARGIN', new_y='NEXT')

        self.ln(5)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(6)

    def add_question(self, num, q_text, q_type, answers, weight=0):
        f = self.f
        weight_str = f'  ({weight} μ.)' if weight else ''
        full_text  = f'{num}.  {strip_html(q_text)}{weight_str}'

        self.set_font(f, 'B', 11)
        self.multi_cell(self.epw, 6, full_text, new_x='LMARGIN', new_y='NEXT')
        self.ln(1)

        if   q_type in (UNIQUE_ANSWER, MULTIPLE_ANSWER):
            self._render_choices(answers, q_type)
        elif q_type == TRUE_FALSE:
            self._render_true_false()
        elif q_type == FREE_TEXT:
            self._render_free_text()
        elif q_type in (FILL_IN_BLANKS, FILL_IN_BLANKS_TOLERANT):
            self._render_fill_blanks(answers)
        elif q_type == MATCHING:
            self._render_matching(answers)
        elif q_type == FILL_IN_FROM_PREDEFINED:
            self._render_fill_predefined(answers)

        self.ln(4)

    # ── Τύποι ερωτήσεων ─────────────────────────────────────────

    def _render_choices(self, answers, q_type):
        self.set_font(self.f, '', 10)
        shuffled = answers[:]
        random.shuffle(shuffled)
        marker = '○  ' if q_type == UNIQUE_ANSWER else '□  '
        for ans in shuffled:
            self.set_x(self.l_margin + 6)
            self.multi_cell(self.epw - 6, 6,
                            f'{marker}{strip_html(ans["answer"])}',
                            new_x='LMARGIN', new_y='NEXT')

    def _render_true_false(self):
        self.set_font(self.f, '', 10)
        self.set_x(self.l_margin + 6)
        self.cell(self.epw - 6, 6,
                  '○  Σωστό          '
                  '○  Λάθος',
                  new_x='LMARGIN', new_y='NEXT')

    def _render_free_text(self):
        self.set_draw_color(160)
        for _ in range(5):
            line_y = self.get_y() + 8
            self.line(self.l_margin + 6, line_y,
                      self.w - self.r_margin - 6, line_y)
            self.ln(10)
        self.set_draw_color(0)

    def _render_fill_blanks(self, answers):
        if not answers:
            return
        self.set_font(self.f, '', 10)
        self.set_x(self.l_margin + 6)
        self.multi_cell(self.epw - 6, 6,
                        _blanks(answers[0].get('answer', '')),
                        new_x='LMARGIN', new_y='NEXT')

    def _render_matching(self, answers):
        f = self.f
        self.set_font(f, '', 10)

        by_pos = {int(a['r_position']): a for a in answers}

        # Αριστερά: όπου correct != 0 (correct = r_position του δεξιού ζεύγους)
        left_pairs = []
        for a in answers:
            correct_pos = int(a.get('correct') or 0)
            if correct_pos and correct_pos in by_pos:
                left_pairs.append((strip_html(a['answer']),
                                   strip_html(by_pos[correct_pos]['answer'])))

        if not left_pairs:
            # fallback: μοίρασε στα δύο
            texts = [strip_html(a['answer']) for a in answers]
            mid   = len(texts) // 2
            left_pairs = list(zip(texts[:mid], texts[mid:]))

        right_col = [r for _, r in left_pairs]
        random.shuffle(right_col)

        col_w = (self.epw - 20) / 2

        self.set_font(f, 'B', 9)
        self.set_x(self.l_margin + 6)
        self.cell(col_w, 6, 'Στήλη Α')
        self.cell(8,     6, '', align='C')
        self.cell(col_w, 6, 'Στήλη Β',
                  new_x='LMARGIN', new_y='NEXT')

        self.set_font(f, '', 10)
        for i, (left_text, _) in enumerate(left_pairs):
            right_text = right_col[i] if i < len(right_col) else ''
            label = chr(65 + i)
            self.set_x(self.l_margin + 6)
            self.cell(col_w, 7, f'{label}. {left_text}')
            self.cell(8,     7, '→', align='C')
            self.cell(col_w, 7, f'{i + 1}. {right_text}',
                      new_x='LMARGIN', new_y='NEXT')

    def _render_fill_predefined(self, answers):
        f = self.f
        self.set_font(f, '', 10)
        for ans in answers:
            raw  = ans.get('answer', '')
            text = raw
            opts = []
            if HAS_PHPSERIALIZE:
                try:
                    arr  = phpserialize.loads(raw.encode('utf-8'), decode_strings=True)
                    text = arr.get(0, '') if isinstance(arr, dict) else str(arr)
                    raw_opts = arr.get(2, {}) if isinstance(arr, dict) else {}
                    opts = list(raw_opts.values()) if isinstance(raw_opts, dict) else list(raw_opts)
                except Exception:
                    pass
            text = _blanks(text)
            self.set_x(self.l_margin + 6)
            self.multi_cell(self.epw - 6, 6, text, new_x='LMARGIN', new_y='NEXT')
            if opts:
                random.shuffle(opts)
                self.set_font(f, '', 9)
                self.set_text_color(80, 80, 80)
                self.set_x(self.l_margin + 6)
                self.cell(self.epw - 6, 5,
                          '(' + ' / '.join(str(o) for o in opts) + ')',
                          new_x='LMARGIN', new_y='NEXT')
                self.set_text_color(0)
                self.set_font(f, '', 10)

# ═══════════════════════════════════════════════════════════════
#  ΔΗΜΙΟΥΡΓΙΑ ZIP
# ═══════════════════════════════════════════════════════════════
def build_zip(course_name, exam_title, exam_date, duration,
              num_groups, per_group, question_ids):
    # 2 queries total regardless of num_groups × per_group
    q_data   = get_questions_by_ids(question_ids)
    ans_data = get_answers_bulk(question_ids)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i in range(num_groups):
            group_label = chr(65 + i)

            pool = question_ids[:]
            random.shuffle(pool)
            group_ids = pool[:per_group]

            pdf = ExamPDF(course_name, exam_title, group_label, exam_date, duration)

            for idx, qid in enumerate(group_ids):
                q = q_data.get(qid)
                if not q:
                    continue
                pdf.add_question(
                    idx + 1,
                    q['question'],
                    int(q['type']),
                    ans_data.get(qid, []),
                    round(float(q['weight'] or 0), 1))

            fname = f'{safe_filename(exam_title)} - OMADA {group_label}.pdf'
            zf.writestr(fname, bytes(pdf.output()))

    buf.seek(0)
    return buf

# ═══════════════════════════════════════════════════════════════
#  FLASK APPLICATION
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
app.secret_key = 'exam_gen_eclass_2025'

TEMPLATE = r"""
<!DOCTYPE html>
<html lang="el">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Εξεταστικές Ομάδες PDF</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" rel="stylesheet">
<style>
  body { background: #f0f2f5; }
  .navbar { background: #1a2340 !important; }
  .card  { border: none; border-radius: 10px; box-shadow: 0 1px 6px rgba(0,0,0,.09); }
  #q-table td, #q-table th { font-size: .85rem; vertical-align: middle; }
  .q-scroll { max-height: 62vh; overflow-y: auto; }
  .badge-type { font-size: .7rem; }
  .sticky-head th { position: sticky; top: 0; background: #fff; z-index: 1; }
</style>
</head>
<body>

<nav class="navbar navbar-dark mb-4">
  <div class="container-fluid">
    <span class="navbar-brand fw-bold">
      <i class="fa fa-file-zipper me-2"></i>Εξεταστικές Ομάδες PDF
    </span>
    {% if not HAS_PHPSERIALIZE %}
    <span class="navbar-text small text-warning">
      <i class="fa fa-triangle-exclamation me-1"></i>
      Για FILL_IN_FROM_PREDEFINED: <code>pip install phpserialize</code>
    </span>
    {% endif %}
  </div>
</nav>

<div class="container-lg">

  {# Flash messages #}
  {% for cat, msg in get_flashed_messages(with_categories=True) %}
  <div class="alert alert-{{ cat }} alert-dismissible fade show">
    {{ msg }}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% endfor %}

  {# ── Επιλογή Μαθήματος ───────────────────────────────────── #}
  <div class="card mb-3 p-3">
    <div class="row align-items-end g-2">
      <div class="col-md-9">
        <label class="form-label fw-bold mb-1">Μάθημα</label>
        <select id="course-sel" class="form-select">
          <option value="">— Επιλέξτε μάθημα —</option>
          {% for c in courses %}
          <option value="{{ c.id }}"
            {% if course and course.id == c.id %}selected{% endif %}>
            [{{ c.code }}] {{ c.title }}
          </option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-3">
        <button class="btn btn-primary w-100" onclick="goToCourse()">
          <i class="fa fa-arrow-right me-1"></i>Φόρτωση
        </button>
      </div>
    </div>
  </div>

  {% if course %}
  {# ── Φίλτρα ─────────────────────────────────────────────── #}
  <div class="card mb-3 p-3">
    <div class="row g-2 align-items-end">
      <div class="col-md-4">
        <label class="form-label small mb-1">Exercise</label>
        <select id="f-ex" class="form-select form-select-sm">
          <option value="">— Όλο το Pool —</option>
          {% for ex in exercises %}
          <option value="{{ ex.id }}"
            {% if sel_exercise == ex.id|string %}selected{% endif %}>
            {{ ex.title }}
          </option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-3">
        <label class="form-label small mb-1">Κατηγορία</label>
        <select id="f-cat" class="form-select form-select-sm">
          <option value="-1">— Όλες —</option>
          {% for cat in categories %}
          <option value="{{ cat.question_cat_id }}"
            {% if sel_category == cat.question_cat_id|string %}selected{% endif %}>
            {{ cat.question_cat_name }}
          </option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-3">
        <label class="form-label small mb-1">Δυσκολία</label>
        <select id="f-diff" class="form-select form-select-sm">
          <option value="-1">— Όλες —</option>
          <option value="1" {% if sel_difficulty == '1' %}selected{% endif %}>Πολύ Εύκολη</option>
          <option value="2" {% if sel_difficulty == '2' %}selected{% endif %}>Εύκολη</option>
          <option value="3" {% if sel_difficulty == '3' %}selected{% endif %}>Μέτρια</option>
          <option value="4" {% if sel_difficulty == '4' %}selected{% endif %}>Δύσκολη</option>
          <option value="5" {% if sel_difficulty == '5' %}selected{% endif %}>Πολύ Δύσκολη</option>
        </select>
      </div>
      <div class="col-md-2">
        <button class="btn btn-outline-secondary btn-sm w-100" onclick="applyFilters()">
          <i class="fa fa-filter me-1"></i>Εφαρμογή
        </button>
      </div>
    </div>
  </div>

  {# ── Κύρια Φόρμα ─────────────────────────────────────────── #}
  <form method="post" action="/generate" id="main-form">
    <input type="hidden" name="course_id" value="{{ course.id }}">

    <div class="row g-3">
      {# Πίνακας ερωτήσεων #}
      <div class="col-lg-8">
        <div class="card p-3">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <h6 class="mb-0">
              Ερωτήσεις
              <span class="badge bg-secondary ms-1">{{ questions|length }}</span>
            </h6>
            <div>
              <button type="button" class="btn btn-sm btn-outline-secondary me-1"
                      onclick="selectAll()">Επιλογή Όλων</button>
              <button type="button" class="btn btn-sm btn-outline-secondary"
                      onclick="selectNone()">Καμία</button>
            </div>
          </div>

          {% if questions %}
          <div class="q-scroll">
            <table class="table table-hover table-sm mb-0" id="q-table">
              <thead class="sticky-head">
                <tr class="table-light">
                  <th style="width:36px">
                    <input type="checkbox" id="check-all" onchange="toggleAll(this)">
                  </th>
                  <th style="width:48px">ID</th>
                  <th>Ερώτηση</th>
                  <th style="width:90px">Τύπος</th>
                  <th style="width:55px">Μον.</th>
                </tr>
              </thead>
              <tbody>
                {% for q in questions %}
                <tr>
                  <td>
                    <input type="checkbox" name="question_ids" value="{{ q.id }}"
                           class="q-cb" onchange="updateCount()">
                  </td>
                  <td class="text-muted">{{ q.id }}</td>
                  <td>{{ q.question | striptags | truncate(90) }}</td>
                  <td>
                    <span class="badge bg-secondary badge-type">
                      {{ qtype_labels.get(q.type, '?') }}
                    </span>
                  </td>
                  <td class="text-muted">{{ q.weight or '—' }}</td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
          {% else %}
          <div class="alert alert-warning mb-0">
            <i class="fa fa-info-circle me-1"></i>
            Δεν βρέθηκαν ερωτήσεις με αυτά τα φίλτρα.
          </div>
          {% endif %}
        </div>
      </div>

      {# Παράμετροι #}
      <div class="col-lg-4">
        <div class="card p-3">
          <h6 class="mb-3">Παράμετροι Εξέτασης</h6>

          <div class="mb-3">
            <label class="form-label small">Τίτλος Εξέτασης <span class="text-danger">*</span></label>
            <input type="text" name="exam_title" class="form-control form-control-sm"
                   value="{{ course.title }}" required>
          </div>
          <div class="mb-3">
            <label class="form-label small">Ημερομηνία</label>
            <input type="text" name="exam_date" class="form-control form-control-sm"
                   placeholder="π.χ. 15/05/2025">
          </div>
          <div class="mb-3">
            <label class="form-label small">Διάρκεια (λεπτά)</label>
            <input type="number" name="duration" class="form-control form-control-sm"
                   min="1" value="45">
          </div>

          <hr>

          <div class="mb-3">
            <label class="form-label small">Αριθμός Ομάδων (1–26) <span class="text-danger">*</span></label>
            <input type="number" name="num_groups" class="form-control form-control-sm"
                   min="1" max="26" value="2" required>
          </div>
          <div class="mb-3">
            <label class="form-label small">Ερωτήσεις ανά Ομάδα <span class="text-danger">*</span></label>
            <input type="number" name="per_group" id="per-group"
                   class="form-control form-control-sm"
                   min="1" value="10" required oninput="updateCount()">
            <div id="count-info" class="form-text mt-1 text-muted">—</div>
          </div>

          <div class="alert alert-info py-2 small">
            <i class="fa fa-info-circle me-1"></i>
            Κάθε ομάδα παίρνει ανεξάρτητη τυχαία σειρά ερωτήσεων και επιλογών.
          </div>

          <button type="submit" class="btn btn-success w-100">
            <i class="fa fa-file-zipper me-2"></i>Δημιουργία ZIP με PDF
          </button>
        </div>
      </div>
    </div>{# /row #}
  </form>
  {% endif %}{# /if course #}

</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
function goToCourse() {
  var id = document.getElementById('course-sel').value;
  if (id) window.location = '/course/' + id;
}

function applyFilters() {
  var cid  = '{{ course.id if course else "" }}';
  var ex   = document.getElementById('f-ex')  ? document.getElementById('f-ex').value   : '';
  var cat  = document.getElementById('f-cat') ? document.getElementById('f-cat').value  : '-1';
  var diff = document.getElementById('f-diff')? document.getElementById('f-diff').value : '-1';
  window.location = '/course/' + cid +
    '?exercise_id=' + ex + '&category_id=' + cat + '&difficulty=' + diff;
}

function selectAll()  { document.querySelectorAll('.q-cb').forEach(c => c.checked = true);  updateCount(); }
function selectNone() { document.querySelectorAll('.q-cb').forEach(c => c.checked = false); updateCount(); }
function toggleAll(master) { document.querySelectorAll('.q-cb').forEach(c => c.checked = master.checked); updateCount(); }

function updateCount() {
  var n   = document.querySelectorAll('.q-cb:checked').length;
  var m   = parseInt((document.getElementById('per-group') || {}).value) || 0;
  var el  = document.getElementById('count-info');
  if (!el) return;
  if (n === 0) { el.innerHTML = '<span class="text-muted">Καμία ερώτηση επιλεγμένη.</span>'; return; }
  var html = '<strong>' + n + '</strong> επιλεγμένες';
  if (m > 0 && n < m)
    html += ' — <span class="text-danger">χρειάζονται τουλάχιστον ' + m + '</span>';
  el.innerHTML = html;
}

var form = document.getElementById('main-form');
if (form) form.addEventListener('submit', function(e) {
  var n = document.querySelectorAll('.q-cb:checked').length;
  var m = parseInt(document.getElementById('per-group').value) || 0;
  if (n === 0) { e.preventDefault(); alert('Επιλέξτε τουλάχιστον μία ερώτηση.'); return; }
  if (n < m)  { e.preventDefault(); alert('Χρειάζονται τουλάχιστον ' + m + ' ερωτήσεις. Έχετε επιλέξει ' + n + '.'); return; }
});

updateCount();
</script>
</body>
</html>
"""

# ── Routes ──────────────────────────────────────────────────────
@app.route('/')
def index():
    courses = get_courses()
    return render_template_string(
        TEMPLATE,
        courses=courses,
        course=None,
        questions=[],
        exercises=[],
        categories=[],
        qtype_labels=QTYPE_LABELS,
        HAS_PHPSERIALIZE=HAS_PHPSERIALIZE,
        sel_exercise=None, sel_category=None, sel_difficulty=None,
    )

@app.route('/course/<int:course_id>')
def course_view(course_id):
    exercise_id = request.args.get('exercise_id') or None
    category_id = request.args.get('category_id', '-1')
    difficulty  = request.args.get('difficulty',  '-1')

    if exercise_id == '':
        exercise_id = None

    courses    = get_courses()
    course     = get_course(course_id)
    exercises  = get_exercises(course_id)
    categories = get_categories(course_id)
    questions  = get_questions(
        course_id,
        exercise_id=int(exercise_id) if exercise_id else None,
        category_id=int(category_id),
        difficulty=int(difficulty),
    )

    return render_template_string(
        TEMPLATE,
        courses=courses,
        course=course,
        questions=questions,
        exercises=exercises,
        categories=categories,
        qtype_labels=QTYPE_LABELS,
        HAS_PHPSERIALIZE=HAS_PHPSERIALIZE,
        sel_exercise=exercise_id,
        sel_category=category_id,
        sel_difficulty=difficulty,
    )

@app.route('/generate', methods=['POST'])
def generate():
    course_id    = int(request.form.get('course_id', 0))
    question_ids = list(map(int, request.form.getlist('question_ids')))
    num_groups   = max(1, min(26, int(request.form.get('num_groups', 2))))
    per_group    = max(1, int(request.form.get('per_group', 10)))
    exam_title   = request.form.get('exam_title', '').strip()
    exam_date    = request.form.get('exam_date',  '').strip()
    duration     = request.form.get('duration',   '').strip()

    if not question_ids:
        flash('Δεν επιλέχθηκε καμία ερώτηση.', 'danger')
        return redirect(url_for('course_view', course_id=course_id))

    if len(question_ids) < per_group:
        flash(
            f'Επιλέχθηκαν {len(question_ids)} ερωτήσεις, '
            f'αλλά χρειάζονται τουλάχιστον {per_group} ανά ομάδα.',
            'danger')
        return redirect(url_for('course_view', course_id=course_id))

    course = get_course(course_id)
    course_name = course['title'] if course else exam_title
    if not exam_title:
        exam_title = course_name

    zip_buf = build_zip(
        course_name, exam_title, exam_date, duration,
        num_groups, per_group, question_ids)

    dl_name = f'{safe_filename(exam_title)} - Exetastikes Omades.zip'
    return send_file(zip_buf, mimetype='application/zip',
                     as_attachment=True, download_name=dl_name)

# ═══════════════════════════════════════════════════════════════
#  ΕΚΚΙΝΗΣΗ
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('=' * 55)
    print('  Εξεταστικές Ομάδες PDF Generator')
    print('=' * 55)
    print(f'  Βάση δεδομένων : {DB_USER}@{DB_HOST}/{DB_NAME}')
    print(f'  Fonts          : {"OK" if os.path.exists(FONT_REGULAR) else "ΔΕΝ ΒΡΕΘΗΚΑΝ — fallback σε Helvetica"}')
    print(f'  phpserialize   : {"OK" if HAS_PHPSERIALIZE else "ΔΕΝ ΕΓΚΑΤΕΣΤΗΜΕΝΟ (pip install phpserialize)"}')
    print(f'  URL            : http://localhost:{APP_PORT}')
    print('=' * 55)
    app.run(debug=False, port=APP_PORT)
