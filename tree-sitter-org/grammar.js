/// <reference types="tree-sitter-cli/dsl" />
// @ts-check

/**
 * tree-sitter-org — Tree-sitter grammar for Org Mode syntax.
 *
 * Implements the formal PEG grammar from docs/plans/syntax.md.
 * Context-sensitive features are handled by src/scanner.c.
 *
 * Design note: _BOL (beginning-of-line) is only used where column-0 is
 * strictly required by Org syntax (headings, footnote definitions, diary
 * sexps). Other elements rely on grammar structure — after _NL, we are
 * always at the start of a line by construction.
 */

// Case-insensitive regex helper
function ci(str) {
  return new RegExp(
    str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
       .replace(/[a-zA-Z]/g, (c) => `[${c.toLowerCase()}${c.toUpperCase()}]`)
  );
}

function sep1(rule, separator) {
  return seq(rule, repeat(seq(separator, rule)));
}

module.exports = grammar({
  name: 'org',

  // External scanner tokens (src/scanner.c)
  externals: $ => [
    $.stars,              // Heading stars at column 0 (e.g. "***")
    $._HEADING_END,      // Close heading on same/higher-level stars or EOI
    $._LIST_START,       // Open a plain list
    $._LIST_END,         // Close a plain list
    $._ITEM_END,         // Terminate a list item
    $._TODO_KW,          // Match current TODO keyword set
    $._BLOCK_END_MATCH,  // Verify #+end_NAME matches #+begin_NAME
    $._GBLOCK_NAME,      // Block name not a lesser block name
    $._MARKUP_OPEN_BOLD,
    $._MARKUP_CLOSE_BOLD,
    $._MARKUP_OPEN_ITALIC,
    $._MARKUP_CLOSE_ITALIC,
    $._MARKUP_OPEN_UNDERLINE,
    $._MARKUP_CLOSE_UNDERLINE,
    $._MARKUP_OPEN_STRIKE,
    $._MARKUP_CLOSE_STRIKE,
    $._MARKUP_OPEN_VERBATIM,
    $._MARKUP_CLOSE_VERBATIM,
    $._MARKUP_OPEN_CODE,
    $._MARKUP_CLOSE_CODE,
    $._PARAGRAPH_CONTINUE,
    $._FNDEF_END,
    $._PLAIN_TEXT,        // Scan to next object boundary
    $._ITEM_TAG_END,      // Rightmost ' :: '
    $._LISTITEM_INDENT,
    $._PLAN_KW_EXT,       // Planning keyword (DEADLINE/SCHEDULED/CLOSED)
    $._ERROR_SENTINEL,
    $._TABLE_START,   // Zero-width gate: emitted once at the start of each org_table
    $._FIXED_WIDTH_COLON, // Consumes optional indent + ':' only at BOL context
  ],

  extras: _ => [],

  conflicts: $ => [
    [$.zeroth_section],
    [$.zeroth_section, $._zs_element],
    [$.item, $.item_tag],
    [$.heading, $.section],
    [$._object, $._object_min],
    // footnote definition vs footnote reference (both start with [fn:LABEL])
    [$.footnote_definition, $._fn_ref_labeled],
  ],

  inline: $ => [
    $._greater_block,
    $._lesser_block,
    $._bullet,
    $._non_affiliatable,
  ],

  word: $ => $._word_token,

  // =========================================================================
  // RULES
  // =========================================================================
  rules: {
    // §2 Document Structure
    document: $ => seq(
      optional($.zeroth_section),
      repeat($.heading),
    ),

    // §3 Headings
    heading: $ => prec.right(seq(
      field('stars', $.stars),
      $._S,
      optional(field('todo', $.todo_keyword)),
      optional(field('priority', $.priority)),
      optional(field('is_comment', $._COMMENT_TOKEN)),
      optional(field('title', $._heading_title)),
      optional(field('tags', $.tags)),
      $._NL,
      optional(field('planning', $.planning)),
      optional(field('properties', $.property_drawer)),
      repeat($._blank_line),
      optional(field('body', $.section)),
      repeat($.heading),
      optional($._HEADING_END),
    )),

    // stars: emitted by external scanner (column 0 + '*'+)
    // Declared in externals — no grammar rule needed.

    todo_keyword: $ => seq(
      $._TODO_KW,
      $._S,
    ),

    priority: $ => seq(
      '[#',
      field('value', choice(/[A-Z]/, /[0-9]+/)),
      ']',
      $._S,
    ),

    _COMMENT_TOKEN: _ => 'COMMENT',

    _heading_title: $ => repeat1($._object_nolb),

    tags: $ => seq(
      ':',
      $.tag,
      repeat(seq(':', $.tag)),
      ':',
    ),

    tag: _ => /[A-Za-z0-9_@#%]+/,

    // §4 Sections
    zeroth_section: $ => choice(
      seq(
        repeat(choice($.special_keyword, $.comment, $._blank_line)),
        field('properties', $.property_drawer),
        repeat(choice($._zs_element, $._blank_line)),
      ),
      seq(
        repeat(choice($.special_keyword, $.comment, $._blank_line)),
        repeat1(choice($._zs_element, $._blank_line)),
      ),
    ),

    section: $ => prec.left(repeat1(choice(
      $._section_element,
      $._blank_line,
    ))),

    // §5 Element Dispatch
    _zs_element: $ => choice(
      $._zs_element_affiliated,
      $.special_keyword,
      $._non_affiliatable,
      $._affiliatable,
    ),

    _zs_element_affiliated: $ => seq(
      repeat1($.caption_keyword),
      $._affiliatable,
    ),

    _section_element: $ => choice(
      $._section_element_affiliated,
      $.special_keyword,
      $._non_affiliatable,
      $._affiliatable,
    ),

    _section_element_affiliated: $ => seq(
      repeat1($.caption_keyword),
      $._affiliatable,
    ),

    _affiliatable: $ => choice(
      $._greater_block,
      $.drawer,
      $.dynamic_block,
      $.footnote_definition,
      $.plain_list,
      $.org_table,
      $.tableel_table,
      $._lesser_block,
      $.diary_sexp,
      $.fixed_width,
      $.horizontal_rule,
      prec(-1, $.paragraph),
    ),

    _non_affiliatable: $ => choice(
      $.comment,
      $.clock,
    ),

    // §6 Greater Elements

    // --- 6.1 Greater Blocks ---
    _greater_block: $ => choice(
      $.center_block,
      $.quote_block,
      $.special_block,
    ),

    center_block: $ => seq(
      token(prec(2, ci('#+begin_center'))),
      optional(field('parameters', $._block_params)),
      $._NL,
      field('body', optional($._gblock_body)),
      token(prec(2, ci('#+end_center'))),
      optional($._TRAILING),
      $._NL,
    ),

    quote_block: $ => seq(
      token(prec(2, ci('#+begin_quote'))),
      optional(field('parameters', $._block_params)),
      $._NL,
      field('body', optional($._gblock_body)),
      token(prec(2, ci('#+end_quote'))),
      optional($._TRAILING),
      $._NL,
    ),

    special_block: $ => seq(
      token(prec(1, ci('#+begin_'))),
      field('name', $._GBLOCK_NAME),
      optional(field('parameters', $._block_params)),
      $._NL,
      field('body', optional($._gblock_body)),
      token(prec(1, ci('#+end_'))),
      $._BLOCK_END_MATCH,
      optional($._TRAILING),
      $._NL,
    ),

    _block_params: $ => seq($._S, $._REST_OF_LINE),

    _gblock_body: $ => repeat1(choice(
      $._section_element,
      $._blank_line,
    )),

    // --- 6.2 Drawers ---
    drawer: $ => seq(
      token(prec(2, ':')),
      field('name', alias($._DRAWER_NAME, $.drawer_name)),
      ':',
      optional($._TRAILING),
      $._NL,
      field('body', optional($._drawer_body)),
      token(prec(2, ci(':end:'))),
      optional($._TRAILING),
      $._NL,
    ),

    _DRAWER_NAME: _ => /[A-Za-z0-9_\-]+/,

    _drawer_body: $ => repeat1(choice(
      $._section_element,
      $._blank_line,
    )),

    // --- 6.3 Dynamic Blocks ---
    dynamic_block: $ => seq(
      token(prec(3, ci('#+begin:'))),
      $._S,
      field('name', alias($._DYNBLOCK_NAME, $.dynamic_block_name)),
      optional(field('parameters', seq($._S, $._REST_OF_LINE))),
      $._NL,
      field('body', optional($._dynblock_body)),
      token(prec(3, ci('#+end:'))),
      optional($._TRAILING),
      $._NL,
    ),

    _DYNBLOCK_NAME: _ => /[^ \t\n]+/,

    _dynblock_body: $ => repeat1(choice(
      $._section_element,
      $._blank_line,
    )),

    // --- 6.4 Footnote Definitions ---
    // Footnote definitions start at column 0 by construction (after NL).
    // Column-0 enforcement is a semantic check, not grammar-level.
    footnote_definition: $ => prec.right(seq(
      '[fn:',
      field('label', alias($._FN_LABEL, $.fn_label)),
      ']',
      optional(field('first_line', seq($._S, repeat($._object)))),
      $._NL,
      optional(field('body', $._fndef_body)),
      optional($._FNDEF_END),
    )),

    _FN_LABEL: _ => /[A-Za-z0-9_\-]+/,

    _fndef_body: $ => repeat1(choice(
      $._section_element,
      $._blank_line,
    )),

    // --- 6.5 Plain Lists and Items ---
    //
    // Design: lists are parsed FLAT — all items (regardless of indentation) are
    // siblings in one plain_list node.  Indented items carry a field('indent',
    // _LISTITEM_INDENT) that records their leading whitespace so that a
    // post-processing step can reconstruct the proper nested structure.
    //
    // Why flat?  Getting tree-sitter to correctly delimit nested plain_list nodes
    // requires the external scanner to peek ahead across newlines, which causes
    // lexer-position corruption between scanner calls in the same scan()
    // invocation (because advances aren't reset until the *whole* scan() returns
    // false).  The flat approach avoids all of that complexity.
    //
    // Blank lines between items are allowed (and hidden from the tree because
    // _blank_line is anonymous).
    plain_list: $ => seq(
      $._LIST_START,
      repeat1(choice($.item, $._blank_line)),
      $._LIST_END,
    ),

    // Items are single-line: bullet (+ optional indent, counter_set, checkbox)
    // followed by either a tag line or a content line.  No multi-line body is
    // parsed at the grammar level; continuation lines are handled in post-
    // processing by examining the indent field of subsequent items.
    item: $ => seq(
      optional(field('indent', $._LISTITEM_INDENT)),
      field('bullet', $._bullet),
      optional(field('counter_set', $.counter_set)),
      optional(field('checkbox', $.checkbox)),
      choice(
        seq(field('tag', $.item_tag), $._NL),
        seq(optional(field('first_line', $._item_first_line)), $._NL),
      ),
    ),

    _item_first_line: $ => repeat1($._object),

    _bullet: $ => choice(
      $._unordered_bullet,
      $._ordered_bullet,
    ),

    _unordered_bullet: $ => seq(
      choice('+', '-', '*'),
      $._S,
    ),

    _ordered_bullet: $ => seq(
      field('counter', alias($._COUNTER, $.counter)),
      choice('.', ')'),
      $._S,
    ),

    _COUNTER: _ => choice(/[0-9]+/, /[a-z]/),

    counter_set: $ => seq(
      '[@',
      choice(/[0-9]+/, /[a-z]/),
      ']',
      $._S,
    ),

    checkbox: $ => seq(
      '[',
      field('status', choice(' ', 'X', '-')),
      ']',
      $._S,
    ),

    item_tag: $ => seq(
      repeat1($._object),
      $._ITEM_TAG_END,
    ),

    // --- 6.6 Property Drawers ---
    property_drawer: $ => seq(
      token(prec(3, ci(':properties:'))),
      optional($._TRAILING),
      $._NL,
      repeat($.node_property),
      token(prec(3, ci(':end:'))),
      optional($._TRAILING),
      $._NL,
    ),

    node_property: $ => seq(
      ':',
      field('name', alias($._PROP_NAME, $.property_name)),
      ':',
      optional(seq($._S, field('value', alias($._REST_OF_LINE, $.property_value)))),
      $._NL,
    ),

    _PROP_NAME: _ => /[^ \t\n:+]+\+?/,

    // --- 6.7 Tables ---
    // $._TABLE_START is a zero-width scanner-gated token emitted exactly once
    // when entering a new org_table.  It tracks in_table state so that
    // consecutive '|'-rows are merged into one org_table rather than creating
    // separate nodes for each row (which is what happens when GLR explores
    // multiple parse paths within zeroth_section / section).
    org_table: $ => prec(1, seq(
      $._TABLE_START,
      repeat1($.table_row),
      repeat($.tblfm_line),
    )),

    table_row: $ => seq(
      /[ \t]*\|/,
      choice(
        field('rule', alias($._table_rule_row, $.table_rule)),
        $._table_std_row,
      ),
      $._NL,
    ),

    _table_rule_row: _ => seq('-', /[^\n]*/),

    _table_std_row: $ => seq(
      $.table_cell,
      repeat(seq('|', $.table_cell)),
      optional('|'),
    ),

    table_cell: $ => choice(
      seq($._S, $._table_cell_objects, optional($._S)),
      seq(optional($._S), $._table_cell_objects, optional($._S)),
      $._S,
    ),

    _table_cell_objects: $ => repeat1($._object_table),

    tblfm_line: $ => seq(
      token(prec(2, ci('#+tblfm:'))),
      optional($._S),
      $._REST_OF_LINE,
      $._NL,
    ),

    tableel_table: $ => prec.left(1, seq(
      $._tableel_first_line,
      repeat($._tableel_cont_line),
    )),

    _tableel_first_line: $ => seq(
      '+',
      '-',
      /[^\n]*/,
      $._NL,
    ),

    _tableel_cont_line: $ => seq(
      choice('|', '+'),
      /[^\n]*/,
      $._NL,
    ),

    // §7 Lesser Elements

    // --- 7.1 Lesser Blocks ---
    _lesser_block: $ => choice(
      $.comment_block,
      $.example_block,
      $.export_block,
      $.src_block,
      $.verse_block,
    ),

    comment_block: $ => seq(
      token(prec(2, ci('#+begin_comment'))),
      optional($._TRAILING),
      $._NL,
      field('body', optional($._raw_block_body)),
      token(prec(2, ci('#+end_comment'))),
      optional($._TRAILING),
      $._NL,
    ),

    example_block: $ => seq(
      token(prec(2, ci('#+begin_example'))),
      optional(field('parameters', $._block_params)),
      $._NL,
      field('body', optional($._gblock_body)),
      token(prec(2, ci('#+end_example'))),
      optional($._TRAILING),
      $._NL,
    ),

    export_block: $ => seq(
      token(prec(2, ci('#+begin_export'))),
      $._S,
      field('backend', alias($._EXPORT_BACKEND, $.export_backend)),
      optional(field('parameters', seq($._S, $._REST_OF_LINE))),
      $._NL,
      field('body', optional($._raw_block_body)),
      token(prec(2, ci('#+end_export'))),
      optional($._TRAILING),
      $._NL,
    ),

    _EXPORT_BACKEND: _ => /[^ \t\n]+/,

    src_block: $ => seq(
      token(prec(2, ci('#+begin_src'))),
      optional(seq(
        $._S,
        field('language', alias($._SRC_LANGUAGE, $.language)),
        optional(seq($._S, field('switches', alias($._REST_OF_LINE, $.src_switches)))),
      )),
      $._NL,
      field('body', optional($.src_block_body)),
      token(prec(2, ci('#+end_src'))),
      optional($._TRAILING),
      $._NL,
    ),

    _SRC_LANGUAGE: _ => /[^ \t\n]+/,

    src_block_body: $ => repeat1($.src_line),

    src_line: _ => seq(/[^\n]*/, '\n'),

    verse_block: $ => seq(
      token(prec(2, ci('#+begin_verse'))),
      optional($._TRAILING),
      $._NL,
      field('body', optional($._gblock_body)),
      token(prec(2, ci('#+end_verse'))),
      optional($._TRAILING),
      $._NL,
    ),

    _raw_block_body: $ => repeat1($._raw_line),

    _raw_line: _ => seq(/[^\n]*/, '\n'),

    _verse_body: $ => repeat1($._verse_line),

    _verse_line: $ => seq(
      repeat($._object),
      $._NL,
    ),

    // --- 7.2 Clock ---
    clock: $ => seq(
      token(prec(2, ci('clock:'))),
      $._S,
      choice(
        seq(field('value', $._inactive_range), $._S, field('duration', $._DURATION)),
        field('value', $._inactive_ts),
        field('duration', $._DURATION),
      ),
      optional($._TRAILING),
      $._NL,
    ),

    _DURATION: _ => seq('=>', /[ \t]+/, /[0-9]+/, ':', /[0-9][0-9]/),

    // --- 7.3 Diary Sexp ---
    // Diary sexps start at column 0 by construction.
    diary_sexp: $ => seq(
      '%%',
      field('value', $._diary_sexp_value),
      optional($._TRAILING),
      $._NL,
    ),

    _diary_sexp_value: _ => seq('(', /[^)\n]*/, ')'),

    // --- 7.4 Planning ---
    planning: $ => prec(2, repeat1($._planning_line)),

    _planning_line: $ => seq(
      $._planning_entry,
      repeat(seq($._S, $._planning_entry)),
      optional($._TRAILING),
      $._NL,
    ),

    _planning_entry: $ => seq(
      field('keyword', alias($._PLAN_KW, $.planning_keyword)),
      ':',
      $._S,
      field('value', $.timestamp),
    ),

    _PLAN_KW: $ => $._PLAN_KW_EXT,

    // --- 7.5 Comments ---
    comment: $ => prec(1, repeat1($._comment_line)),

    _comment_line: $ => choice(
      seq('#', ' ', optional(field('value', /[^\n]*/)), $._NL),
      seq('#', $._NL),
    ),

    // --- 7.6 Fixed-Width Areas ---
    fixed_width: $ => prec(1, repeat1($._fixed_width_line)),

    // _FIXED_WIDTH_COLON (external) enforces the BOL constraint from the spec:
    //   _fixed_width_line <- _BOL _INDENT? ':' (' ' value:[^\n]* / &_NL) _NL
    // The scanner only emits this token when ':' is the first non-whitespace
    // character on the line (column 0, or column > 0 after list-scanner
    // positioning with prev_char == 0). It consumes the optional leading
    // indentation and the ':' itself.
    _fixed_width_line: $ => choice(
      seq($._FIXED_WIDTH_COLON, ' ', optional(field('value', /[^\n]*/)), $._NL),
      seq($._FIXED_WIDTH_COLON, $._NL),
    ),

    // --- 7.7 Horizontal Rules ---
    horizontal_rule: $ => seq(
      token(prec(2, /-----(-)*/)),
      optional($._TRAILING),
      $._NL,
    ),

    // --- 7.8 Special Keywords ---
    special_keyword: $ => seq(
      '#+',
      field('key', alias($._SPECIAL_KEY, $.keyword_key)),
      ':',
      optional(seq($._S, field('value', alias($._REST_OF_LINE, $.keyword_value)))),
      $._NL,
    ),

    _SPECIAL_KEY: _ => token(prec(2, choice(
      ci('TITLE'), ci('AUTHOR'), ci('DATE'), ci('EMAIL'),
      ci('DESCRIPTION'), ci('KEYWORDS'), ci('LANGUAGE'),
      ci('CATEGORY'), ci('FILETAGS'), ci('TAGS'),
      ci('TODO'), ci('SEQ_TODO'), ci('TYP_TODO'),
      ci('PRIORITIES'), ci('PROPERTY'), ci('STARTUP'),
      ci('ARCHIVE'), ci('COLUMNS'), ci('OPTIONS'),
    ))),

    // --- 7.9 Affiliated Keywords ---
    caption_keyword: $ => seq(
      token(prec(2, ci('#+caption'))),
      optional(field('optval', $._caption_optval)),
      ':',
      optional(field('value', seq($._S, repeat1($._object_nofn)))),
      $._NL,
    ),

    _caption_optval: $ => seq(
      '[',
      repeat(choice(
        /[^\[\]\n]/,
        seq('[', repeat(/[^\[\]\n]/), ']'),
      )),
      ']',
    ),

    // --- 7.10 Paragraphs ---
    paragraph: $ => prec(-1, repeat1($._paragraph_line)),

    _paragraph_line: $ => seq(
      repeat1($._object),
      $._NL,
    ),

    // §8 Objects

    // --- 8.1 Export Snippets ---
    export_snippet: $ => seq(
      '@@',
      field('backend', alias($._BACKEND, $.snippet_backend)),
      ':',
      optional(field('value', alias($._snippet_value, $.snippet_value))),
      '@@',
    ),

    _BACKEND: _ => /[A-Za-z0-9\-]+/,
    _snippet_value: _ => /([^@\n]|@[^@])+/,

    // --- 8.2 Footnote References ---
    footnote_reference: $ => choice(
      $._fn_ref_inline,
      $._fn_ref_anonymous,
      $._fn_ref_labeled,
    ),

    _fn_ref_labeled: $ => seq(
      '[fn:',
      field('label', alias($._FN_LABEL, $.fn_label)),
      ']',
    ),

    _fn_ref_inline: $ => seq(
      '[fn:',
      field('label', alias($._FN_LABEL, $.fn_label)),
      ':',
      field('definition', repeat1($._object)),
      ']',
    ),

    _fn_ref_anonymous: $ => seq(
      '[fn::',
      field('definition', repeat1($._object)),
      ']',
    ),

    // --- 8.3 Citations ---
    citation: $ => seq(
      '[cite',
      optional(field('style', $._cite_style)),
      ':',
      optional($._S),
      optional(field('prefix', $._cite_global_prefix)),
      field('references', $._cite_references),
      optional(field('suffix', $._cite_global_suffix)),
      optional($._S),
      ']',
    ),

    _cite_style: $ => seq(
      '/',
      field('style', alias(/[A-Za-z0-9_\-]+/, $.cite_style_name)),
      optional(seq('/', field('variant', alias(/[A-Za-z0-9_\-\/]+/, $.cite_variant)))),
    ),

    _cite_global_prefix: $ => seq(
      repeat1($._object),
      ';',
    ),

    _cite_references: $ => prec.left(sep1($.citation_reference, ';')),

    _cite_global_suffix: $ => seq(
      ';',
      repeat1($._object),
    ),

    // --- 8.4 Citation References ---
    citation_reference: $ => seq(
      optional(field('prefix', $._cite_key_prefix)),
      '@',
      field('key', alias($._CITE_KEY, $.cite_key)),
      optional(field('suffix', $._cite_key_suffix)),
    ),

    _cite_key_prefix: $ => repeat1($._object_min),
    _CITE_KEY: _ => /[A-Za-z0-9\-.:?!`'/*@+|(){}<>&_^$#%~]+/,
    _cite_key_suffix: $ => repeat1($._object_min),

    // --- 8.5 Inline Source Blocks ---
    inline_source_block: $ => seq(
      'src_',
      field('language', alias($._INLINE_LANG, $.inline_language)),
      optional(field('headers', $._inline_headers_group)),
      '{',
      field('body', optional(alias($._inline_body, $.inline_body))),
      '}',
    ),

    _INLINE_LANG: _ => /[^ \t\n\[{]+/,
    _inline_headers_group: $ => seq('[', alias($._inline_headers, $.inline_headers), ']'),
    _inline_headers: _ => /[^\]\n]*/,
    _inline_body: _ => /[^}\n]*/,

    // --- 8.6 Line Breaks ---
    line_break: _ => seq(token(prec(1, '\\\\')), /[ \t]*/),

    // --- 8.7 Links ---
    plain_link: $ => seq(
      field('type', alias($._LINK_TYPE, $.link_type)),
      ':',
      field('path', alias($._PATH_PLAIN, $.link_path)),
    ),

    _LINK_TYPE: _ => token(choice(
      'shell', 'news', 'mailto', 'https', 'http',
      'ftp', 'help', 'file', 'elisp',
    )),

    _PATH_PLAIN: _ => /[^ \t\n\[\]<>()]+/,

    angle_link: $ => seq(
      '<',
      field('type', alias($._LINK_TYPE, $.link_type)),
      ':',
      field('path', alias(/[^>\n]*/, $.link_path)),
      '>',
    ),

    regular_link: $ => choice(
      seq('[[', field('path', alias($._link_path, $.link_path)), ']]'),
      seq(
        '[[',
        field('path', alias($._link_path, $.link_path)),
        '][',
        field('description', $._link_description),
        ']]',
      ),
    ),

    _link_path: _ => /([^\[\]\\]|\\]|\\\\)*/,

    _link_description: $ => repeat1($._object_min),

    // radio_link — deferred to Python post-processing
    radio_link: $ => repeat1($._object_min),

    // --- 8.8 Targets and Radio Targets ---
    target: $ => seq(
      '<<',
      field('value', alias($._TARGET_TEXT, $.target_text)),
      '>>',
    ),

    _TARGET_TEXT: _ => /[^<>\n]+/,

    radio_target: $ => seq(
      '<<<',
      field('body', repeat1($._object_min)),
      '>>>',
    ),

    // --- 8.9 Timestamps ---
    timestamp: $ => choice(
      $._active_range,
      $._inactive_range,
      $._active_range_sameday,
      $._inactive_range_sameday,
      $._active_ts,
      $._inactive_ts,
    ),

    _active_ts: $ => seq('<', $._ts_inner, '>'),
    _active_range: $ => seq('<', $._ts_inner, '>', '--', '<', $._ts_inner, '>'),
    _active_range_sameday: $ => seq(
      '<', $._ts_date, $._S,
      field('time_start', alias($._ts_time, $.ts_time)), '-',
      field('time_end', alias($._ts_time, $.ts_time)),
      optional(seq($._S, $._ts_modifiers)), '>',
    ),

    _inactive_ts: $ => seq('[', $._ts_inner, ']'),
    _inactive_range: $ => seq('[', $._ts_inner, ']', '--', '[', $._ts_inner, ']'),
    _inactive_range_sameday: $ => seq(
      '[', $._ts_date, $._S,
      field('time_start', alias($._ts_time, $.ts_time)), '-',
      field('time_end', alias($._ts_time, $.ts_time)),
      optional(seq($._S, $._ts_modifiers)), ']',
    ),

    _ts_inner: $ => seq(
      field('date', $._ts_date),
      optional(field('time', seq($._S, alias($._ts_time, $.ts_time)))),
      optional(field('modifiers', seq($._S, $._ts_modifiers))),
    ),

    _ts_date: $ => prec.right(seq(
      field('year', alias($._YYYY, $.ts_year)),
      '-',
      field('month', alias($._MM, $.ts_month)),
      '-',
      field('day', alias($._DD, $.ts_day)),
      optional(field('dayname', seq($._S, alias($._ts_dayname, $.ts_dayname)))),
    )),

    _YYYY: _ => /[0-9]{4}/,
    _MM: _ => /[0-9]{2}/,
    _DD: _ => /[0-9]{2}/,
    _ts_dayname: _ => /[^ \t\n+\-\]>0-9]+/,
    _ts_time: _ => /[0-9]{1,2}:[0-9]{2}/,

    _ts_modifiers: $ => choice(
      seq($._ts_repeater, optional(seq($._S, $._ts_delay))),
      seq($._ts_delay, optional(seq($._S, $._ts_repeater))),
    ),

    _ts_repeater: $ => seq(
      field('mark', alias($._REPEATER_MARK, $.repeater_mark)),
      field('value', /[0-9]+/),
      field('unit', alias($._TIME_UNIT, $.time_unit)),
      optional(seq(
        '/',
        field('cap_value', /[0-9]+/),
        field('cap_unit', alias($._TIME_UNIT, $.time_unit)),
      )),
    ),

    _REPEATER_MARK: _ => token(choice('++', '.+', '+')),

    _ts_delay: $ => seq(
      field('mark', alias($._DELAY_MARK, $.delay_mark)),
      field('value', /[0-9]+/),
      field('unit', alias($._TIME_UNIT, $.time_unit)),
    ),

    _DELAY_MARK: _ => token(choice('--', '-')),
    _TIME_UNIT: _ => /[hdwmy]/,

    // --- 8.10 Text Markup ---
    bold: $ => seq(
      $._MARKUP_OPEN_BOLD,
      field('body', repeat1($._object)),
      $._MARKUP_CLOSE_BOLD,
    ),

    italic: $ => seq(
      $._MARKUP_OPEN_ITALIC,
      field('body', repeat1($._object)),
      $._MARKUP_CLOSE_ITALIC,
    ),

    underline: $ => seq(
      $._MARKUP_OPEN_UNDERLINE,
      field('body', repeat1($._object)),
      $._MARKUP_CLOSE_UNDERLINE,
    ),

    strike_through: $ => seq(
      $._MARKUP_OPEN_STRIKE,
      field('body', repeat1($._object)),
      $._MARKUP_CLOSE_STRIKE,
    ),

    verbatim: $ => seq(
      $._MARKUP_OPEN_VERBATIM,
      field('body', alias($._verbatim_body, $.verbatim_content)),
      $._MARKUP_CLOSE_VERBATIM,
    ),

    _verbatim_body: _ => /[^\n=]+/,

    code: $ => seq(
      $._MARKUP_OPEN_CODE,
      field('body', alias($._code_body, $.code_content)),
      $._MARKUP_CLOSE_CODE,
    ),

    _code_body: _ => /[^\n~]+/,

    // --- 8.11 Plain Text ---
    // Plain text is handled by the external scanner to keep prev_char
    // tracking coherent for markup PRE/POST constraints.
    plain_text: $ => $._PLAIN_TEXT,

    // §9 Object Sets
    _object: $ => choice(
      $.export_snippet, $.footnote_reference, $.citation,
      $.inline_source_block, $.line_break,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    _object_nolb: $ => choice(
      $.export_snippet, $.footnote_reference, $.citation,
      $.inline_source_block,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    _object_nofn: $ => choice(
      $.export_snippet, $.citation,
      $.inline_source_block, $.line_break,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    _object_min: $ => choice(
      $.export_snippet, $.inline_source_block, $.line_break,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    _object_table: $ => choice(
      $.export_snippet, $.footnote_reference, $.citation,
      $.inline_source_block,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    // §10 Lexical Primitives
    _S: _ => /[ \t]+/,
    _NL: _ => /\n/,
    _INDENT: _ => token(prec(-1, /[ \t]+/)),
    _TRAILING: _ => /[ \t]+/,
    _REST_OF_LINE: _ => /[^\n]+/,

    _blank_line: _ => token(prec(-1, /[ \t]*\n/)),

    _word_token: _ => /[A-Za-z][A-Za-z0-9_]*/,
  },
});
