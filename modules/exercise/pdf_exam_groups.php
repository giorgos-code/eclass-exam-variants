<?php

/*
 * ========================================================================
 * Open eClass - PDF Exam Groups Generator
 * ========================================================================
 * Δημιουργία ZIP με ξεχωριστά PDF τεστ ανά ομάδα (Α, Β, Γ...)
 * με τυχαία επιλογή και ανακάτεμα ερωτήσεων/απαντήσεων.
 * ========================================================================
 */

require_once 'exercise.class.php';
require_once 'question.class.php';
require_once 'answer.class.php';

$require_editor = true;
$require_current_course = true;

require_once '../../include/baseTheme.php';

$toolName  = $langExercices;
$pageName  = $langCreateExamGroups;
$navigation[] = ['url' => "index.php?course=$course_code",        'name' => $langExercices];
$navigation[] = ['url' => "question_pool.php?course=$course_code", 'name' => $langQuestionPool];

// ─────────────────────────────────────────────────────────────────────────────
// POST: παραγωγή ZIP με ξεχωριστά PDFs
// ─────────────────────────────────────────────────────────────────────────────
if (isset($_POST['generate'])) {
    if (!isset($_POST['token']) || !validate_csrf_token($_POST['token'])) {
        csrf_token_error();
    }

    $question_ids = array_map('intval', $_POST['question_ids'] ?? []);
    $num_groups   = max(1, min(26, intval($_POST['num_groups'])));
    $per_group    = max(1, intval($_POST['per_group']));
    $exam_title   = trim($_POST['exam_title']) ?: $currentCourseName;
    $exam_date    = trim($_POST['exam_date']);
    $exam_duration = trim($_POST['exam_duration']);

    if (count($question_ids) < $per_group) {
        Session::flash('message', sprintf($langNotEnoughQuestions, $per_group));
        Session::flash('alert-class', 'alert-warning');
        redirect_to_home_page("modules/exercise/pdf_exam_groups.php?course=$course_code");
    }

    // mPDF config (ίδια με export.php)
    $defaultConfig     = (new Mpdf\Config\ConfigVariables())->getDefaults();
    $defaultFontConfig = (new Mpdf\Config\FontVariables())->getDefaults();
    $mpdf_config = [
        'tempDir' => _MPDF_TEMP_PATH,
        'fontDir' => array_merge($defaultConfig['fontDir'], [$webDir . '/template/modern/fonts']),
        'fontdata' => $defaultFontConfig['fontdata'] + [
            'opensans' => [
                'R'  => 'open-sans-v13-greek_cyrillic_latin_greek-ext-regular.ttf',
                'B'  => 'open-sans-v13-greek_cyrillic_latin_greek-ext-700.ttf',
                'I'  => 'open-sans-v13-greek_cyrillic_latin_greek-ext-italic.ttf',
                'BI' => 'open-sans-v13-greek_cyrillic_latin_greek-ext-700italic.ttf',
            ],
            'roboto' => [
                'R' => 'roboto-v15-latin_greek_cyrillic_greek-ext-regular.ttf',
                'I' => 'roboto-v15-latin_greek_cyrillic_greek-ext-italic.ttf',
            ],
        ],
    ];

    $zip_tmp  = tempnam(sys_get_temp_dir(), 'examzip_') . '.zip';
    $zip      = new ZipArchive();
    $zip->open($zip_tmp, ZipArchive::CREATE | ZipArchive::OVERWRITE);

    for ($i = 0; $i < $num_groups; $i++) {
        $group_label = chr(65 + $i); // A, B, C …

        // Κάθε ομάδα: ανεξάρτητο shuffle → πάρε τις M πρώτες
        $pool = $question_ids;
        shuffle($pool);
        $group_ids = array_slice($pool, 0, $per_group);

        $html = build_exam_html(
            $group_ids, $exam_title, $group_label,
            $exam_date, $exam_duration, $currentCourseName, $course_code
        );

        $mpdf = new Mpdf\Mpdf($mpdf_config);
        $mpdf->setFooter('{DATE j-n-Y} || {PAGENO}/{nb}');
        $mpdf->SetCreator(course_id_to_prof($course_id));
        $mpdf->SetAuthor(course_id_to_prof($course_id));
        $mpdf->WriteHTML($html);

        $safe_title = preg_replace('/[^A-Za-z0-9_\-\. ]/', '', $exam_title);
        $zip->addFromString("{$safe_title} - {$langGroupLabel} {$group_label}.pdf",
                            $mpdf->Output('', 'S'));
    }

    $zip->close();

    // Καθαρισμός οποιουδήποτε buffered output πριν στείλουμε το binary ZIP
    while (ob_get_level()) {
        ob_end_clean();
    }

    $dl_name = preg_replace('/[^A-Za-z0-9_\-\. ]/', '', $exam_title) . " - {$langExamGroups}.zip";
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="' . $dl_name . '"');
    header('Content-Length: ' . filesize($zip_tmp));
    header('Pragma: no-cache');
    header('Expires: 0');
    readfile($zip_tmp);
    unlink($zip_tmp);
    exit;
}

// ─────────────────────────────────────────────────────────────────────────────
// GET: φόρμα επιλογής
// ─────────────────────────────────────────────────────────────────────────────

$fromExercise = isset($_GET['fromExercise']) ? intval($_GET['fromExercise']) : 0;
$categoryId   = isset($_GET['categoryId'])   ? intval($_GET['categoryId'])   : -1;
$difficultyId = isset($_GET['difficultyId']) ? intval($_GET['difficultyId']) : -1;

$query_vars = [$course_id];
$extraSql   = '';
if ($difficultyId > -1) { $query_vars[] = $difficultyId; $extraSql .= ' AND eq.difficulty = ?d'; }
if ($categoryId   > -1) { $query_vars[] = $categoryId;   $extraSql .= ' AND eq.category = ?d'; }

if ($fromExercise > 0) {
    $query_vars[] = $fromExercise;
    $questions = Database::get()->queryArray(
        "SELECT eq.id, eq.question, eq.type, eq.difficulty, eq.category, eq.weight
           FROM exercise_question eq
           JOIN exercise_with_questions ewq ON eq.id = ewq.question_id
          WHERE eq.course_id = ?d $extraSql AND ewq.exercise_id = ?d
          ORDER BY ewq.q_position",
        $query_vars
    );
} else {
    $questions = Database::get()->queryArray(
        "SELECT eq.id, eq.question, eq.type, eq.difficulty, eq.category, eq.weight
           FROM exercise_question eq
          WHERE eq.course_id = ?d $extraSql
          ORDER BY eq.question",
        $query_vars
    );
}

$categories = Database::get()->queryArray(
    "SELECT question_cat_id, question_cat_name FROM exercise_question_cats
      WHERE course_id = ?d ORDER BY question_cat_name", $course_id);
$exercises = Database::get()->queryArray(
    "SELECT id, title FROM exercise WHERE course_id = ?d ORDER BY title", $course_id);

// Difficulty labels (same as statement_admin)
$diff_labels = [
    0 => $langQuestionNotDefined ?? '-',
    1 => $langQuestionVeryEasy   ?? '1',
    2 => $langQuestionEasy       ?? '2',
    3 => $langQuestionModerate   ?? '3',
    4 => $langQuestionDifficult  ?? '4',
    5 => $langQuestionVeryDifficult ?? '5',
];

// ── action bar ───────────────────────────────────────────────────────────────
$tool_content .= action_bar([
    ['title' => $langBack, 'url' => "question_pool.php?course=$course_code", 'icon' => 'fa-reply', 'level' => 'primary-label'],
]);

// ── alerts ───────────────────────────────────────────────────────────────────
if (Session::has('message')) {
    $tool_content .= "<div class='alert " . Session::get('alert-class') . "'>" . Session::get('message') . "</div>";
}

// ── φίλτρα ───────────────────────────────────────────────────────────────────
$filter_exercise_sel = '';
foreach ($exercises as $ex) {
    $sel = ($fromExercise == $ex->id) ? 'selected' : '';
    $filter_exercise_sel .= "<option value='{$ex->id}' $sel>" . q($ex->title) . "</option>";
}
$filter_cat_sel = "<option value='-1'" . ($categoryId == -1 ? ' selected' : '') . ">-- {$langAllCategories} --</option>";
foreach ($categories as $cat) {
    $sel = ($categoryId == $cat->question_cat_id) ? 'selected' : '';
    $filter_cat_sel .= "<option value='{$cat->question_cat_id}' $sel>" . q($cat->question_cat_name) . "</option>";
}
$diff_options = "<option value='-1'" . ($difficultyId == -1 ? ' selected' : '') . ">-- {$langAllOfThem} --</option>";
foreach ($diff_labels as $val => $lbl) {
    $sel = ($difficultyId == $val) ? 'selected' : '';
    $diff_options .= "<option value='$val' $sel>" . q($lbl) . "</option>";
}

$tool_content .= "
<form method='get' action='' class='form-horizontal mb-4'>
<input type='hidden' name='course' value='$course_code'>
<div class='row g-2 align-items-end'>
  <div class='col-md-4'>
    <label class='control-label-notes mb-1'>$langExercice</label>
    <select name='fromExercise' class='form-select'>
      <option value='0'" . ($fromExercise == 0 ? ' selected' : '') . ">-- $langQuestionPool --</option>
      $filter_exercise_sel
    </select>
  </div>
  <div class='col-md-3'>
    <label class='control-label-notes mb-1'>$langQuestionCat</label>
    <select name='categoryId' class='form-select'>$filter_cat_sel</select>
  </div>
  <div class='col-md-3'>
    <label class='control-label-notes mb-1'>$langQuestionDiffGrade</label>
    <select name='difficultyId' class='form-select'>$diff_options</select>
  </div>
  <div class='col-md-2'>
    <button type='submit' class='btn submitAdminBtn w-100'>$langFilter</button>
  </div>
</div>
</form>";

// ── λίστα ερωτήσεων ──────────────────────────────────────────────────────────
$tool_content .= "
<form method='post' action='?course=$course_code' id='exam-groups-form'>
" . generate_csrf_token_form_field() . "

<div class='row g-4'>
  <!-- Στήλη ερωτήσεων -->
  <div class='col-lg-8'>
    <div class='card p-3'>
      <div class='d-flex justify-content-between align-items-center mb-2'>
        <h5 class='mb-0'>$langSelectQuestions (" . count($questions) . ")</h5>
        <div>
          <button type='button' class='btn btn-sm btn-outline-secondary me-1' id='btn-select-all'>$langSelectAll</button>
          <button type='button' class='btn btn-sm btn-outline-secondary' id='btn-deselect-all'>$langJSDeselectAll</button>
        </div>
      </div>";

if (empty($questions)) {
    $tool_content .= "<div class='alert alert-warning'>$langNoQuestionsFound</div>";
} else {
    $tool_content .= "<div class='table-responsive'><table class='table-default table-sm' id='questions-table'>
      <thead><tr>
        <th style='width:40px'><input type='checkbox' id='check-all'></th>
        <th>#ID</th>
        <th>$langQuestion</th>
        <th>$langType</th>
        <th>$langQuestionCat</th>
        <th>$langQuestionDiffGrade</th>
      </tr></thead><tbody>";

    foreach ($questions as $q) {
        $objQ = new Question();
        $objQ->read($q->id);
        $cat_name  = $objQ->selectCategoryName($q->category) ?: '-';
        $type_name = $objQ->selectTypeLegend($q->type);
        $diff_name = $diff_labels[$q->difficulty] ?? '-';
        $q_title   = q(mb_strimwidth(strip_tags($q->question), 0, 80, '…'));

        $tool_content .= "
        <tr>
          <td><input type='checkbox' name='question_ids[]' value='{$q->id}' class='q-checkbox'></td>
          <td>{$q->id}</td>
          <td>$q_title</td>
          <td><small>$type_name</small></td>
          <td><small>$cat_name</small></td>
          <td><small>$diff_name</small></td>
        </tr>";
    }
    $tool_content .= "</tbody></table></div>";
}

$tool_content .= "</div></div>

  <!-- Στήλη παραμέτρων -->
  <div class='col-lg-4'>
    <div class='card p-3'>
      <h5 class='mb-3'>$langExamParameters</h5>

      <div class='mb-3'>
        <label class='control-label-notes mb-1'>$langExamTitle <span class='Accent-200-cl'>(*)</span></label>
        <input type='text' name='exam_title' class='form-control' required
               placeholder='$langExamTitle' value='" . q($currentCourseName) . "'>
      </div>
      <div class='mb-3'>
        <label class='control-label-notes mb-1'>$langExamDate</label>
        <input type='text' name='exam_date' class='form-control'
               placeholder='πχ. 15/05/2025'>
      </div>
      <div class='mb-3'>
        <label class='control-label-notes mb-1'>$langExamDuration</label>
        <input type='number' name='exam_duration' class='form-control' min='1' value='45'>
      </div>

      <hr>

      <div class='mb-3'>
        <label class='control-label-notes mb-1'>$langNumGroups <span class='Accent-200-cl'>(*)</span></label>
        <input type='number' name='num_groups' class='form-control' min='1' max='26' value='2' required>
        <small class='text-muted'>$langNumGroupsInfo</small>
      </div>
      <div class='mb-3'>
        <label class='control-label-notes mb-1'>$langQuestionsPerGroup <span class='Accent-200-cl'>(*)</span></label>
        <input type='number' name='per_group' id='per_group' class='form-control' min='1' value='10' required>
        <small class='text-muted' id='questions-selected-info'></small>
      </div>

      <div class='mb-3 alert alert-info py-2'>
        <small><i class='fa fa-info-circle me-1'></i>$langExamGroupsInfo</small>
      </div>

      <button type='submit' name='generate' class='btn submitAdminBtn w-100'>
        <i class='fa fa-file-zipper me-1'></i> $langGenerateExamZIP
      </button>
    </div>
  </div>

</div><!-- row -->
</form>";

// ── JavaScript ────────────────────────────────────────────────────────────────
$tool_content .= "
<script>
$(function() {
    // Select all / deselect
    $('#check-all, #btn-select-all').on('click', function() {
        $('.q-checkbox').prop('checked', true);
        $('#check-all').prop('checked', true);
        updateCount();
    });
    $('#btn-deselect-all').on('click', function() {
        $('.q-checkbox').prop('checked', false);
        $('#check-all').prop('checked', false);
        updateCount();
    });
    $('.q-checkbox, #check-all').on('change', updateCount);

    function updateCount() {
        var n = $('.q-checkbox:checked').length;
        var m = parseInt($('#per_group').val()) || 0;
        var msg = n + ' " . addslashes($langQuestionsSelected) . "';
        if (m > 0 && n < m) {
            msg += ' &mdash; <span class=\"text-danger\">" . addslashes($langNeedAtLeast) . " ' + m + '</span>';
        }
        $('#questions-selected-info').html(msg);
    }
    $('#per_group').on('input', updateCount);
    updateCount();

    // Validation before submit
    $('#exam-groups-form').on('submit', function(e) {
        var n = $('.q-checkbox:checked').length;
        var m = parseInt($('#per_group').val()) || 0;
        if (n === 0) {
            e.preventDefault();
            alert('" . addslashes($langSelectAtLeastOne) . "');
            return false;
        }
        if (n < m) {
            e.preventDefault();
            alert('" . addslashes($langNotEnoughQuestionsJS) . " ' + m + '.');
            return false;
        }
    });
});
</script>";

draw($tool_content, 2, null, $head_content);

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Δημιουργεί το πλήρες HTML ενός τεστ για μία ομάδα.
 */
function build_exam_html(array $question_ids, string $exam_title, string $group_label,
                         string $exam_date, string $exam_duration,
                         string $course_name, string $course_code): string
{
    $duration_str = $exam_duration ? "{$exam_duration} λεπτά" : '';
    $date_str     = $exam_date     ? $exam_date                : '';

    $html = "<!DOCTYPE html>
<html lang='el'>
<head>
<meta charset='utf-8'>
<style>
  * { font-family: 'opensans'; }
  body { font-size: 11pt; margin: 0; padding: 0; }
  .header { border-bottom: 2px solid #000; padding-bottom: 6px; margin-bottom: 16px; }
  .header-top { display: flex; justify-content: space-between; align-items: flex-start; }
  .header-left h1 { font-size: 13pt; margin: 0 0 2px; }
  .header-left h2 { font-size: 11pt; font-weight: normal; margin: 0; color: #333; }
  .group-badge { font-size: 22pt; font-weight: bold; border: 3px solid #000;
                 padding: 4px 16px; text-align: center; }
  .meta { font-size: 9pt; color: #444; margin-top: 6px; }
  .student-box { border: 1px solid #888; padding: 6px 10px; margin: 10px 0 16px;
                 font-size: 10pt; }
  .student-box table { width: 100%; border-collapse: collapse; }
  .student-box td { padding: 3px 6px; border: none; }
  .question-block { margin-bottom: 14px; page-break-inside: avoid; }
  .question-text { font-weight: bold; margin-bottom: 6px; }
  .q-num { display: inline-block; min-width: 24px; }
  .options-table { width: 100%; border-collapse: collapse; margin-left: 24px; }
  .options-table td { padding: 3px 6px; vertical-align: top; font-size: 10.5pt; }
  .opt-box { display: inline-block; width: 14px; height: 14px; border: 1px solid #333;
             border-radius: 50%; margin-right: 4px; vertical-align: middle; }
  .opt-box-sq { display: inline-block; width: 14px; height: 14px; border: 1px solid #333;
                margin-right: 4px; vertical-align: middle; }
  .free-text-area { margin-left: 24px; margin-top: 4px; }
  .free-text-line { border-bottom: 1px solid #bbb; height: 18px; margin-bottom: 6px; }
  .matching-table { width: 90%; border-collapse: collapse; margin-left: 24px; }
  .matching-table td { padding: 4px 8px; border: 1px solid #ccc; font-size: 10pt; }
  .fill-blank { display: inline-block; min-width: 60px; border-bottom: 1px solid #000; }
  h2 { font-size: 12pt; border-bottom: 1px solid black; }
</style>
</head>
<body>

<div class='header'>
  <div class='header-top'>
    <div class='header-left'>
      <h1>" . q($course_name) . "</h1>
      <h2>" . q($exam_title) . "</h2>
    </div>
    <div class='group-badge'>{$langGroupLabel}&nbsp;{$group_label}</div>
  </div>
  <div class='meta'>
    " . ($date_str     ? "<strong>{$langExamDate}:</strong> {$date_str} &nbsp;&nbsp;" : '') . "
    " . ($duration_str ? "<strong>{$langExamDuration}:</strong> {$duration_str}"      : '') . "
  </div>
</div>

<div class='student-box'>
  <table><tr>
    <td style='width:55%'><strong>{$langSurnameName}:</strong> _______________________________</td>
    <td style='width:25%'><strong>Α.Μ.:</strong> _______________</td>
    <td style='width:20%'><strong>Τμήμα:</strong> ___________</td>
  </tr></table>
</div>";

    foreach ($question_ids as $idx => $qid) {
        $question = new Question();
        if (!$question->read($qid)) {
            continue;
        }

        $num          = $idx + 1;
        $q_title      = q_math($question->selectTitle());
        $q_desc       = $question->selectDescription();
        $q_type       = $question->selectType();
        $q_weight     = round($question->selectWeighting(), 1);
        $weight_label = $q_weight > 0 ? " <small style='font-weight:normal;color:#555;'>({$q_weight} {$langPoints})</small>" : '';

        $html .= "
<div class='question-block'>
  <div class='question-text'>
    <span class='q-num'>{$num}.</span> {$q_title}{$weight_label}
  </div>
  " . ($q_desc ? "<div style='margin-left:24px;margin-bottom:6px;font-size:10pt;'>{$q_desc}</div>" : '') . "
  " . exam_question_html($question, $qid, $q_type) . "
</div>";
    }

    $html .= "</body></html>";
    return $html;
}

/**
 * Αποδίδει τις επιλογές μιας ερώτησης χωρίς να δείχνει ποια είναι σωστή.
 * Πάντα κάνει shuffle τις επιλογές.
 */
function exam_question_html(Question $question, int $qid, int $type): string
{
    global $langPoints;

    if ($type == ORAL) {
        return '';
    }

    $answer    = new Answer($qid);
    $nbr       = $answer->selectNbrAnswers();
    if ($nbr == 0) {
        return '';
    }

    // Φτιάχνουμε λίστα με IDs 1..N και κάνουμε shuffle
    $answer_ids = range(1, $nbr);
    if ($type == UNIQUE_ANSWER || $type == MULTIPLE_ANSWER) {
        shuffle($answer_ids); // ανακάτεμα επιλογών
    }

    $html = '';

    if ($type == UNIQUE_ANSWER || $type == MULTIPLE_ANSWER || $type == TRUE_FALSE) {
        $box_class = ($type == MULTIPLE_ANSWER) ? 'opt-box-sq' : 'opt-box';
        $html .= "<table class='options-table'>";
        foreach ($answer_ids as $aid) {
            $title = standard_text_escape($answer->getTitle($aid));
            $html .= "<tr><td style='width:20px'><span class='{$box_class}'></span></td>
                          <td>{$title}</td></tr>";
        }
        $html .= "</table>";

    } elseif ($type == FREE_TEXT) {
        $html .= "<div class='free-text-area'>";
        for ($l = 0; $l < 5; $l++) {
            $html .= "<div class='free-text-line'></div>";
        }
        $html .= "</div>";

    } elseif ($type == FILL_IN_BLANKS || $type == FILL_IN_BLANKS_TOLERANT) {
        // Δείχνουμε κείμενο με [______] αντί για τη σωστή λέξη
        $raw = $answer->getTitle(1);
        list($text, ) = Question::blanksSplitAnswer($raw);
        $display = preg_replace('/\[[^\]]*\]/', '<span class="fill-blank">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>', standard_text_escape($text));
        $html .= "<div style='margin-left:24px;font-size:10pt;'>{$display}</div>";

    } elseif ($type == FILL_IN_FROM_PREDEFINED_ANSWERS) {
        for ($aid = 1; $aid <= $nbr; $aid++) {
            $raw   = $answer->getTitle($aid);
            $arr   = unserialize($raw);
            $text  = $arr[0] ?? '';
            $opts  = $arr[2] ?? [];
            shuffle($opts);
            $opts_str = implode(' / ', array_map('q', $opts));
            $display  = preg_replace('/\[[^\]]*\]/',
                "<span class='fill-blank'>&nbsp;&nbsp;&nbsp;&nbsp;</span>",
                standard_text_escape($text));
            $html .= "<div style='margin-left:24px;font-size:10pt;'>{$display}</div>
                      <div style='margin-left:24px;font-size:9pt;color:#555;'>({$opts_str})</div>";
        }

    } elseif ($type == MATCHING) {
        // Αριστερά: στοιχεία | Δεξιά: ανακατεμένα ζεύγη
        $left  = [];
        $right = [];
        for ($aid = 1; $aid <= $nbr; $aid++) {
            if ($answer->isCorrect($aid)) {
                $left[]  = standard_text_escape($answer->getTitle($aid));
                $right[] = standard_text_escape($answer->answer[$answer->isCorrect($aid)]);
            }
        }
        shuffle($right);
        $html .= "<table class='matching-table'><tr>
                    <th style='width:45%'>A</th><th style='width:10%'></th><th style='width:45%'>B</th>
                  </tr>";
        $max = max(count($left), count($right));
        for ($r = 0; $r < $max; $r++) {
            $l_cell = isset($left[$r])  ? $left[$r]  : '';
            $r_cell = isset($right[$r]) ? $right[$r] : '';
            $html .= "<tr><td>{$l_cell}</td><td style='text-align:center'>→</td><td>{$r_cell}</td></tr>";
        }
        $html .= "</table>";
    }

    return $html;
}
