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
    $._TODO_KW,          // Match current TODO keyword set
    $._COMMENT_TOKEN,    // Match 'COMMENT' heading indicator at word boundary
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
    $._INDENT_PARAGRAPH_CONTINUE,
    $._INDENT_LIST_ITEM_CONTINUE,
    $._INDENT_CONTENT_CONTINUE,
    $._FNDEF_END,
    $._PLAIN_TEXT,        // Scan to next object boundary
    $._ITEM_TAG_END,      // Rightmost ' :: '
    $._INDENT_BEGIN,
    $._INDENT_END,
    $._PLAN_KW_EXT,       // Planning keyword (DEADLINE/SCHEDULED/CLOSED)
    $._DYNBLOCK_SYNC,     // Zero-width sync point for dynamic-block boundaries
    $._TODO_SETUP_SYNC,   // Zero-width sync point to update TODO keyword set
    $._AFFILIATED_SYNC,   // Zero-width sync point for affiliated-keyword boundaries
    $._DRAWER_ENTER_SYNC, // Zero-width sync point to enter drawer context
    $._DRAWER_EXIT_SYNC,  // Zero-width sync point to exit drawer context
    $._ERROR_SENTINEL,
    $._TABLE_START,   // Zero-width gate: emitted once at the start of each org_table
    $._TABLE_BREAK_SYNC, // Zero-width sync: emitted only when current table must end
    $._FIXED_WIDTH_COLON, // Consumes optional indent + ':' only at BOL context
    $._INLINE_BABEL_START, // Consumes 'call_' when followed by a valid function-name start
    $._INLINE_SRC_START,   // Consumes 'src_' when followed by a valid language-name start
    $._INLINE_BABEL_OUTSIDE_HEADER_START, // Consumes '[' in inline call suffix context
  ],

  extras: _ => [],

  conflicts: $ => [
    [$.zeroth_section],
    [$.zeroth_section, $._zs_element],
    [$.list_item, $.item_tag],
    [$.heading, $.section],
    [$.heading, $._section_element],
    [$.heading, $._affiliatable_no_block],
    [$._object, $._object_min],
    [$._object, $._object_nofn],
    [$.regular_link, $._PROP_REST_OF_LINE],
    [$.regular_link, $._DRAWER_KV_REST],
    [$.drawer, $._affiliatable_no_drawer],
    [$.logbook_drawer, $._affiliatable_no_drawer],
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
      optional(field('comment', $.comment_keyword)),
      optional(field('title', $._heading_title)),
      optional(field('tags', $.tags)),
      $._NL,
      optional(field('planning', $.planning)),
      optional(field('properties', $.property_drawer)),
      repeat($.blank_line),
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

    comment_keyword: $ => $._COMMENT_TOKEN,

    priority: $ => seq(
      '[#',
      field('value', $.priority_value),
      ']',
      $._S,
    ),

    priority_value: _ => /[a-zA-Z0-9]+/,

    _heading_title: $ => repeat1($._object_nolb),

    tags: $ => seq(
      ':',
      $.tag,
      repeat(seq(':', $.tag)),
      ':',
    ),

    tag: _ => /[A-Za-z0-9_@#%]+/,

    // §4 Sections
    zeroth_section: $ => prec.left(repeat1(choice(
      $._zs_content,
      $.blank_line,
    ))),

    section: $ => prec.left(repeat1(choice(
      $._section_content,
      $.blank_line,
    ))),

    _zs_content: $ => choice(
      $.indent,
      $._zs_element_no_block,
    ),

    _section_content: $ => choice(
      $.indent,
      $._section_element_no_block,
    ),

    // §5 Element Dispatch
    _zs_element: $ => choice(
      $._zs_element_affiliated,
      $.special_keyword,
      $._non_affiliatable,
      $._affiliatable,
    ),

    _zs_element_no_block: $ => choice(
      $.special_keyword,
      $._affiliated_keyword,
      $._non_affiliatable,
      $._affiliatable_no_block,
    ),

    _zs_element_affiliated: $ => seq(
      repeat1($._affiliated_keyword),
      $._affiliatable,
    ),

    _section_element: $ => choice(
      $._section_element_affiliated,
      $.special_keyword,
      $._non_affiliatable,
      $._affiliatable,
    ),

    _section_element_no_block: $ => choice(
      $.special_keyword,
      $._affiliated_keyword,
      $._non_affiliatable,
      $._affiliatable_no_block,
    ),

    _section_element_affiliated: $ => seq(
      repeat1($._affiliated_keyword),
      $._affiliatable,
    ),

    _section_element_affiliated_no_drawer: $ => seq(
      repeat1($._affiliated_keyword),
      $._affiliatable_no_drawer,
    ),

    _affiliatable: $ => choice(
      $.indent,
      $._greater_block,
      $.property_drawer,
      $.drawer,
      $.logbook_drawer,
      $.dynamic_block,
      $.footnote_definition,
      $.list,
      $.org_table,
      $.tableel_table,
      $._lesser_block,
      $.diary_sexp,
      $.fixed_width,
      alias($.lone_end_line, $.paragraph),
      $.horizontal_rule,
      prec(-1, $.paragraph),
    ),

    indent: $ => prec.right(seq(
      field('indent', alias($._INDENT_BEGIN, $.whitespace)),
      $._block,
    )),

    _block: $ => seq(
      field('body', choice(
        $.blank_line,
        $.indent,
        $._block_section_element_no_block,
      )),
      repeat(field('body', choice(
        $.blank_line,
        $.indent,
        prec(-6, seq($._INDENT, $.property_drawer)),
        prec(-5, seq($._INDENT_CONTENT_CONTINUE, $._block_section_element_no_block)),
      ))),
      $._INDENT_END,
    ),

    _block_section_element_no_block: $ => choice(
      $.special_keyword,
      $._affiliated_keyword,
      $._non_affiliatable,
      alias($._block_list, $.list),
      $._affiliatable_no_block_no_list_paragraph,
      alias($._block_paragraph, $.paragraph),
    ),

    _affiliatable_no_block_no_list_paragraph: $ => choice(
      $._greater_block,
      $.property_drawer,
      $.drawer,
      $.logbook_drawer,
      $.dynamic_block,
      $.footnote_definition,
      $.org_table,
      $.tableel_table,
      $._lesser_block,
      $.diary_sexp,
      $.fixed_width,
      alias($.lone_end_line, $.paragraph),
      $.horizontal_rule,
    ),

    _affiliatable_no_block: $ => choice(
      $._greater_block,
      $.property_drawer,
      $.drawer,
      $.logbook_drawer,
      $.dynamic_block,
      $.footnote_definition,
      $.list,
      $.org_table,
      $.tableel_table,
      $._lesser_block,
      $.diary_sexp,
      $.fixed_width,
      alias($.lone_end_line, $.paragraph),
      $.horizontal_rule,
      prec(-1, $.paragraph),
    ),

    _affiliatable_no_drawer: $ => choice(
      $._greater_block,
      $.dynamic_block,
      $.footnote_definition,
      $.list,
      $.org_table,
      $.tableel_table,
      $._lesser_block,
      $.diary_sexp,
      $.fixed_width,
      $.horizontal_rule,
      prec(-1, $.paragraph),
    ),

    _affiliatable_no_drawer_no_paragraph: $ => choice(
      $._greater_block,
      $.dynamic_block,
      $.footnote_definition,
      $.list,
      $.org_table,
      $.tableel_table,
      $._lesser_block,
      $.diary_sexp,
      $.fixed_width,
      $.horizontal_rule,
    ),

    _drawer_element: $ => choice(
      $._section_element_affiliated_no_drawer,
      $.special_keyword,
      $._non_affiliatable,
      $._affiliatable_no_drawer,
    ),

    _logbook_drawer_element: $ => choice(
      $._section_element_affiliated_no_drawer,
      $.special_keyword,
      $._non_affiliatable,
      $._affiliatable_no_drawer_no_paragraph,
    ),

    _non_affiliatable: $ => choice(
      $.comment,
      $.clock,
      $.babel_call,
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
      token(prec(2, /[ \t]*#\+end_center/i)),
      optional($._TRAILING),
      $._NL,
    ),

    quote_block: $ => seq(
      token(prec(2, ci('#+begin_quote'))),
      optional(field('parameters', $._block_params)),
      $._NL,
      field('body', optional($._gblock_body)),
      token(prec(2, /[ \t]*#\+end_quote/i)),
      optional($._TRAILING),
      $._NL,
    ),

    special_block: $ => seq(
      token(prec(1, ci('#+begin_'))),
      field('name', $._GBLOCK_NAME),
      optional(field('parameters', $._block_params)),
      $._NL,
      field('body', optional($._gblock_body)),
      token(prec(1, /[ \t]*#\+end_/i)),
      $._BLOCK_END_MATCH,
      optional($._TRAILING),
      $._NL,
    ),

    _block_params: $ => seq($._S, $._REST_OF_LINE),

    _gblock_body: $ => repeat1(choice(
      seq($._INDENT, $._section_element),
      $._section_element,
      $.blank_line,
    )),

    // --- 6.2 Drawers ---
    drawer: $ => seq(
      token(prec(2, ':')),
      field('name', alias($._DRAWER_NAME, $.drawer_name)),
      choice(
        seq(':', $._NL),
        seq(':', field('body', $.drawer_start_text), $._NL),
      ),
      $._DRAWER_ENTER_SYNC,
      field('body', optional($._drawer_body)),
      token(prec(2, /[ \t]*:end:/i)),
      optional(choice(
        $._TRAILING,
        field('end_text', alias($._REST_OF_LINE, $.plain_text)),
      )),
      $._NL,
      $._DRAWER_EXIT_SYNC,
    ),

    _DRAWER_NAME: _ => token(choice(
      /[A-DF-Za-df-z0-9_\-][A-Za-z0-9_\-]*/,
      /[Ee][A-MO-Za-mo-z0-9_\-][A-Za-z0-9_\-]*/,
      /[Ee][Nn][A-CE-Za-ce-z0-9_\-][A-Za-z0-9_\-]*/,
      /[Ee][Nn][Dd][A-Za-z0-9_\-]+/,
    )),

    drawer_start_text: _ => /[^\n]+/,

    _drawer_body: $ => repeat1($._drawer_body_line),

    _logbook_drawer_body: $ => repeat1($._logbook_drawer_body_line),

    _drawer_body_line: $ => choice(
      $.blank_line,
      $.indent,
      seq(optional($._INDENT), choice(
        $.drawer_kv_line,
        $.drawer_double_colon_line,
        $._drawer_element,
      )),
    ),

    _logbook_drawer_body_line: $ => choice(
      $.blank_line,
      $.indent,
      seq(optional($._INDENT), choice(
        $.drawer_kv_line,
        $.drawer_double_colon_line,
        $._logbook_drawer_element,
      )),
    ),

    drawer_kv_line: $ => prec(1, seq(
      ':',
      /[^:\n]+/,
      ':',
      choice(
        seq(
          $._S,
          choice(
            $.regular_link,
            $.timestamp,
            prec(-1, $._DRAWER_KV_REST),
          ),
        ),
        optional($._TRAILING),
      ),
      $._NL,
    )),

    _DRAWER_KV_REST: _ => /[^\n\[][^\n]*/,

    drawer_double_colon_line: $ => seq(
      /[^:\n \t][^\n]*::[^\n]*/,
      $._NL,
    ),

    // --- 6.3 LOGBOOK Drawers ---
    logbook_drawer: $ => seq(
      token(prec(3, ci(':logbook:'))),
      choice(
        $._NL,
        seq(field('body', $.drawer_start_text), $._NL),
      ),
      $._DRAWER_ENTER_SYNC,
      field('body', optional($._logbook_drawer_body)),
      token(prec(3, /[ \t]*:end:/i)),
      optional(choice(
        $._TRAILING,
        field('end_text', alias($._REST_OF_LINE, $.plain_text)),
      )),
      $._NL,
      $._DRAWER_EXIT_SYNC,
    ),

    // --- 6.4 Dynamic Blocks ---
    dynamic_block: $ => seq(
      token(prec(3, ci('#+begin:'))),
      $._S,
      field('name', alias($._DYNBLOCK_NAME, $.dynamic_block_name)),
      optional(field('parameters', seq($._S, $._REST_OF_LINE))),
      $._NL,
      field('body', optional($._dynblock_body)),
      token(prec(3, /[ \t]*#\+end:/i)),
      optional($._TRAILING),
      $._NL,
      $._DYNBLOCK_SYNC,
    ),

    _DYNBLOCK_NAME: _ => /[^ \t\n]+/,

    _dynblock_body: $ => repeat1(choice(
      seq($._INDENT, $._section_element),
      $._section_element,
      $.blank_line,
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
      seq($._INDENT, $._section_element),
      $._section_element,
      $.blank_line,
    )),

    // --- 6.5 List Items ---
    //
    list: $ => prec.right(repeat1(field('item', $.list_item))),

    _block_list: $ => prec.right(5, seq(
      field('item', $.list_item),
      repeat(seq($._INDENT_LIST_ITEM_CONTINUE, field('item', $.list_item))),
    )),

    list_item: $ => prec.right(seq(
      field('bullet', $._bullet),
      optional(field('counter_set', $.counter_set)),
      optional(field('checkbox', $.checkbox)),
      choice(
        prec(2, seq(
          field('tag', $.item_tag),
          field('first_line', $._item_first_line_target_end),
          field('first_line', alias($._TRAILING, $.plain_text)),
          $._NL,
        )),
        prec(2, seq(
          field('first_line', $._item_first_line_target_end),
          field('first_line', alias($._TRAILING, $.plain_text)),
          $._NL,
        )),
        prec(1, seq(
          field('tag', $.item_tag),
          optional(field('first_line', $._item_first_line)),
          optional($._TRAILING),
          $._NL,
        )),
        seq(optional(field('first_line', $._item_first_line)), optional($._TRAILING), $._NL),
      ),
      optional(prec.dynamic(5, $._list_item_body)),
    )),

    _list_item_body: $ => seq(
      $._INDENT_BEGIN,
      $._block,
    ),

    _item_first_line: $ => repeat1($._object),

    _item_first_line_target_end: $ => prec.right(3, seq(
      repeat($._object_nofn),
      choice(
        $.code,
        $.verbatim,
        $.bold,
        $.italic,
        $.underline,
        $.strike_through,
        $.regular_link,
        $.angle_link,
        $.plain_link,
        $.timestamp,
        $.completion_counter,
        $.entity,
        $.macro,
        $.target,
        $.radio_target,
        $.export_snippet,
        $.footnote_reference,
        $.citation,
        $.inline_source_block,
        $.inline_babel_call,
      ),
    )),

    _bullet: $ => choice(
      $.unordered_bullet,
      $._ordered_bullet,
    ),

    unordered_bullet: _ => token(/[+*-][ \t]+/),

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

    completion_counter: $ => seq(
      '[',
      field('value', $.completion_counter_value),
      ']',
    ),

    completion_counter_value: _ => token(choice(
      /[0-9]*\/[0-9]*/,
      /[0-9]*%/,
    )),

    item_tag: $ => seq(
      repeat1($._object),
      $._ITEM_TAG_END,
    ),

    // --- 6.6 Property Drawers ---
    property_drawer: $ => prec(4, seq(
      token(prec(3, /[ \t]*:[Pp][Rr][Oo][Pp][Ee][Rr][Tt][Ii][Ee][Ss]:/)),
      optional($._TRAILING),
      $._NL,
      $._DRAWER_ENTER_SYNC,
      repeat(choice(
        $.blank_line,
        seq(optional($._INDENT), $.node_property),
      )),
      token(prec(3, /[ \t]*:end:/i)),
      optional(choice(
        $._TRAILING,
        field('end_text', alias($._REST_OF_LINE, $.plain_text)),
      )),
      $._NL,
      $._DRAWER_EXIT_SYNC,
    )),

    node_property: $ => seq(
      ':',
      field('name', alias($._PROP_NAME, $.property_name)),
      ':',
      choice(
        seq($._S, field('value', choice(
          prec(1, alias($._PROP_MALFORMED_LINK_REST, $.property_value)),
          seq(
            alias($._PROP_REGULAR_LINK, $.regular_link),
            optional(alias($._PROP_REST_OF_LINE, $.property_value)),
          ),
          $.timestamp,
          prec(-1, alias($._PROP_REST_OF_LINE, $.property_value)),
        ))),
        optional($._TRAILING),
      ),
      $._NL,
    ),

    _PROP_REST_OF_LINE: _ => /[^\n\[][^\n]*/,

    _PROP_MALFORMED_LINK_REST: _ => choice(
      /\[\[[^\n]*\]\]\][^\n]*/,
      /\[\[[^\n]*\[\[[^\n]*/,
    ),

    _PROP_REGULAR_LINK: $ => prec(1, choice(
      seq('[[', field('path', alias($._PROP_LINK_PATH, $.link_path)), ']]'),
      seq(
        '[[',
        field('path', alias($._PROP_LINK_PATH, $.link_path)),
        '][',
        field('description', $._link_description),
        ']]',
      ),
    )),

    _PROP_LINK_PATH: $ => repeat1(choice(
      alias($._PROP_LINK_PATH_TEXT, $.plain_text),
      alias($._PROP_LINK_PATH_ESC, $.plain_text),
      '[',
      ']',
    )),

    _PROP_LINK_PATH_TEXT: _ => /[^\\\[\]]+/,
    _PROP_LINK_PATH_ESC: _ => /\\./,

    _PROP_NAME: _ => /[^ \t\n:+]+\+?/,

    // --- 6.7 Tables ---
    // $._TABLE_START is a zero-width scanner-gated token emitted exactly once
    // when entering a new org_table.  It tracks in_table state so that
    // consecutive '|'-rows are merged into one org_table rather than creating
    // separate nodes for each row (which is what happens when GLR explores
    // multiple parse paths within zeroth_section / section).
    org_table: $ => prec(1, seq(
      $._TABLE_START,
      repeat1(seq(optional($._INDENT), $.table_row)),
      repeat($.tblfm_line),
      $._TABLE_BREAK_SYNC,
    )),

    table_row: $ => seq(
      '|',
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
      alias($._S, $.plain_text),
    ),

    _table_cell_objects: $ => repeat1($._object_table),

    tblfm_line: $ => seq(
      optional($._INDENT),
      token(prec(2, ci('#+tblfm:'))),
      optional($._S),
      $._REST_OF_LINE,
      $._NL,
    ),

    tableel_table: _ => token(prec(1,
      /[ \t]*\+-[^\n]*\n(?:[ \t]*\|[^\n]*\n|[ \t]*\+-[^\n]*\n)+/
    )),

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
      field('body', optional($.comment_block_body)),
      token(prec(3, /[ \t]*#\+end_comment/i)),
      optional($._TRAILING),
      $._NL,
    ),

    example_block: $ => seq(
      token(prec(2, ci('#+begin_example'))),
      optional(field('parameters', $._block_params)),
      $._NL,
      field('body', optional($.example_block_body)),
      token(prec(3, /[ \t]*#\+end_example/i)),
      optional($._TRAILING),
      $._NL,
    ),

    example_block_body: $ => repeat1($.example_line),

    example_line: _ => seq(/[^\n]*/, '\n'),

    comment_block_body: $ => repeat1($.comment_line),

    comment_line: _ => seq(/[^\n]*/, '\n'),

    export_block: $ => seq(
      token(prec(2, ci('#+begin_export'))),
      $._S,
      field('backend', alias($._EXPORT_BACKEND, $.export_backend)),
      optional(field('parameters', seq($._S, $._REST_OF_LINE))),
      $._NL,
      field('body', optional($.export_block_body)),
      token(prec(3, /[ \t]*#\+end_export/i)),
      optional($._TRAILING),
      $._NL,
    ),

    _EXPORT_BACKEND: _ => /[^ \t\n]+/,

    export_block_body: $ => repeat1($.export_line),

    export_line: _ => seq(/[^\n]*/, '\n'),

    src_block: $ => seq(
      token(prec(2, ci('#+begin_src'))),
      optional(seq(
        $._S,
        field('language', alias($._SRC_LANGUAGE, $.language)),
        optional(seq($._S, field('switches', alias($._REST_OF_LINE, $.src_switches)))),
      )),
      $._NL,
      field('body', optional($.src_block_body)),
      token(prec(3, /[ \t]*#\+end_src/i)),
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
      token(prec(3, /[ \t]*#\+end_verse/i)),
      optional($._TRAILING),
      $._NL,
    ),

    _indented_object_line: $ => seq(
      $._PARAGRAPH_CONTINUE,
      repeat1($._object),
    ),

    _verse_body: $ => repeat1($._verse_line),

    _verse_line: $ => seq(
      repeat($._object),
      $.newline,
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
      optional($._INDENT),
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
      seq($._FIXED_WIDTH_COLON, ' ', optional(field('value', alias(/[^\n]*/, $.fixed_width_value))), $._NL),
      seq($._FIXED_WIDTH_COLON, $._NL),
    ),

    // --- 7.7 Horizontal Rules ---
    horizontal_rule: $ => seq(
      token(prec(2, /-----(-)*/)),
      optional($._TRAILING),
      $._NL,
    ),

    lone_end_line: $ => seq(
      alias(token(prec(10, /:end:/i)), $.plain_text),
      $.newline,
    ),

    // --- 7.8 Special Keywords ---
    special_keyword: $ => choice(
      seq(
        '#+',
        field('key', alias($._TODO_SPECIAL_KEY, $.keyword_key)),
        ':',
        $._TODO_SETUP_SYNC,
        optional(seq($._S, field('value', alias($._REST_OF_LINE, $.keyword_value)))),
        $._NL,
      ),
      seq(
        '#+',
        field('key', alias($._SPECIAL_KEY_NO_TODO, $.keyword_key)),
        ':',
        optional(seq($._S, field('value', alias($._REST_OF_LINE, $.keyword_value)))),
        $._NL,
      ),
    ),

    _TODO_SPECIAL_KEY: _ => token(prec(2, ci('TODO'))),

    _SPECIAL_KEY_NO_TODO: _ => token(prec(1, /[A-Za-z][A-Za-z0-9_-]*/)),

    // --- 7.9 Affiliated Keywords ---
    _affiliated_keyword: $ => choice(
      $.caption_keyword,
      $.tblname_keyword,
      $.results_keyword,
      $.plot_keyword,
    ),

    caption_keyword: $ => seq(
      token(prec(2, ci('#+caption'))),
      optional(field('optval', $._caption_optval)),
      ':',
      $._AFFILIATED_SYNC,
      optional(field('value', seq($._S, alias($._REST_OF_LINE, $.plain_text)))),
      $._NL,
    ),

    tblname_keyword: $ => seq(
      token(prec(2, ci('#+tblname'))),
      ':',
      $._AFFILIATED_SYNC,
      optional(field('value', seq($._S, alias($._REST_OF_LINE, $.plain_text)))),
      $._NL,
    ),

    results_keyword: $ => seq(
      token(prec(2, ci('#+results'))),
      ':',
      $._AFFILIATED_SYNC,
      optional(field('value', seq($._S, alias($._REST_OF_LINE, $.plain_text)))),
      $._NL,
    ),

    plot_keyword: $ => seq(
      token(prec(2, ci('#+plot'))),
      ':',
      $._AFFILIATED_SYNC,
      optional(field('value', seq($._S, alias($._REST_OF_LINE, $.plain_text)))),
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

    // --- 7.11 Babel Calls (top-level) ---
    // #+call: NAME[H1](ARGS)[H2]
    babel_call: $ => seq(
      token(prec(2, ci('#+call:'))),
      $._S,
      field('name', alias($._BABEL_CALL_NAME, $.call_name)),
      optional($._babel_inside_header),
      '(',
      field('arguments', optional(alias($._BABEL_ARGS, $.call_arguments))),
      ')',
      optional($._babel_outside_header),
      optional($._TRAILING),
      $._NL,
    ),

    _BABEL_CALL_NAME: _ => /[^ \t\n\[\]()]+/,
    _BABEL_ARGS: _ => /[^)\n]+/,
    _BABEL_HEADER: _ => /[^\]\n]+/,
    _BABEL_INLINE_HEADER: _ => /[^\]\n]*/,

    _babel_inside_header: $ => seq(
      '[',
      field('inside_header', alias($._BABEL_HEADER, $.call_inside_header)),
      ']',
    ),

    _babel_outside_header: $ => seq(
      '[',
      field('outside_header', alias($._BABEL_HEADER, $.call_outside_header)),
      ']',
    ),

    _babel_outside_header_inline: $ => seq(
      $._INLINE_BABEL_OUTSIDE_HEADER_START,
      field('outside_header', alias($._BABEL_INLINE_HEADER, $.call_outside_header)),
      ']',
    ),

    // --- 7.10 Paragraphs ---
    paragraph: $ => prec(-1, repeat1($._paragraph_line)),

    _block_paragraph: $ => prec.right(2, seq(
      $._paragraph_line,
      repeat($._block_paragraph_continuation_line),
    )),

    _block_paragraph_continuation_line: $ => seq(
      $._INDENT_PARAGRAPH_CONTINUE,
      repeat1($._object),
      $.newline,
    ),

    _paragraph_line: $ => seq(
      choice(
        $._timestamp_paragraph_line,
        repeat1($._object),
        $._indented_object_line,
      ),
      $.newline,
    ),

    _timestamp_paragraph_line: $ => seq(
      $.timestamp,
      $._S,
      repeat1($._object),
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
      field('definition', $._fn_ref_def),
      ']',
    ),

    _fn_ref_anonymous: $ => seq(
      '[fn::',
      field('definition', $._fn_ref_def),
      ']',
    ),

    _fn_ref_def: $ => repeat1(choice(
      $._object,
      $.newline,
    )),

    // --- 8.3 Citations ---
    citation: $ => seq(
      '[cite',
      optional(field('style', $._cite_style)),
      ':',
      optional($._S),
      optional(field('body', alias($._CITE_BODY, $.citation_body))),
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
    _CITE_KEY: _ => /[A-Za-z0-9\-.:?!`'/*+|(){}<>&_^$#%~]+/,
    _cite_key_suffix: $ => repeat1($._object_min),

    _CITE_BODY: _ => /[^\]]+/,

    // --- 8.5 Inline Source Blocks ---
    // _INLINE_SRC_START is an external token that consumes 'src_' only when
    // followed by a valid language-name start character.  This ensures the
    // external scanner (not the plain_text scanner) controls the token boundary
    // so the GLR parser can choose inline_source_block over plain_text.
    inline_source_block: $ => seq(
      $._INLINE_SRC_START,
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

    // --- 8.5b Inline Babel Calls ---
    // call_NAME[H1](ARGS)[H2]
    // _INLINE_BABEL_START is an external token that consumes 'call_' only when
    // followed by a valid function-name start character, giving the scanner
    // priority over TOKEN_PLAIN_TEXT so the GLR parser can recognise the rule.
    // _INLINE_BABEL_OUTSIDE_HEADER_START keeps a trailing '[...]' suffix from
    // being consumed as plain_text after the argument list closes.
    // prec.right resolves the optional-outside-header shift/reduce conflict.
    inline_babel_call: $ => prec.right(seq(
        $._INLINE_BABEL_START,
        field('name', alias($._BABEL_CALL_NAME, $.call_name)),
        optional($._babel_inside_header),
        '(',
        field('arguments', optional(alias($._BABEL_ARGS, $.call_arguments))),
        ')',
        optional($._babel_outside_header_inline),
    )),

    // --- 8.5c Macros ---
    // {{{NAME}}}  |  {{{NAME(ARGUMENTS)}}}
    // No external token needed: '{{{' is not ambiguous in plain_text since the
    // scanner stops at '{{{' followed by a letter (see scanner.c).
    macro: $ => seq(
      '{{{',
      field('name', alias($._MACRO_NAME, $.macro_name)),
      optional(seq(
        '(',
        field('arguments', optional(alias($._MACRO_ARGS, $.macro_arguments))),
        ')',
      )),
      '}}}',
    ),

    _MACRO_NAME: _ => /[A-Za-z][A-Za-z0-9_\-]*/,
    // Argument content: any char except ')', newline, or the start of '}}}'.
    // Stops before ')' so the enclosing seq can consume it.
    _MACRO_ARGS: _ => /([^})\n]|}[^})\n]|}}[^})\n])*/,

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
      choice(
        seq(
          field('type', alias($._LINK_TYPE, $.link_type)),
          ':',
          field('path', alias(/[^>]*/, $.link_path)),
        ),
        field('path', alias($._ANGLE_EMAIL_PATH, $.link_path)),
      ),
      '>',
    ),

    _ANGLE_EMAIL_PATH: _ => /[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z0-9-]+/,

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

    _link_path: _ => /([^\[\]]|\\.)*/,

    _link_description: $ => repeat1(choice(
      alias($._LINK_DESC_TEXT, $.plain_text),
      ']',
      $.newline,
    )),

    _LINK_DESC_TEXT: _ => /[^\]\n]+/,

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

    _verbatim_body: _ => /[^\n=]+( = [^\n=]+|==+[^\n=]*|=[^ \t\n=\-.,;:!?')}\["\\|*\/_+~][^\n=]*)*/,

    code: $ => seq(
      $._MARKUP_OPEN_CODE,
      field('body', alias($._code_body, $.code_content)),
      $._MARKUP_CLOSE_CODE,
    ),

    _code_body: _ => /[^\n~]+( ~ [^\n~]+|~~+[^\n~]*|~[^ \t\n~\-.,;:!?')}\["\\|*\/_+=][^\n~]*)*/,

    // --- 8.11 Entities ---
    // §11.1 (now promoted to supported): \NAME POST  |  \NAME{}  |  \_SPACES
    // Two forms:
    //   named:   \NAME  where NAME is [A-Za-z]+, optionally followed by {}
    //   nbsp:    \_     followed by one or more spaces (non-breaking space)
    // Name validation against org-entities is a @semantic post-processing step.
    //
    // Implemented as a single atomic token so that the {} suffix is matched
    // before the external _PLAIN_TEXT scanner can consume it as plain text.
    // The name (and has_braces flag) are extracted from the source slice by
    // the Python layer rather than being named children of the node.
    entity: _ => token(choice(
      /\\[A-Za-z]+\{\}/,
      /\\[A-Za-z]+/,
      /\\_[ \t]+/,
    )),

    // --- 8.12 Subscript / Superscript ---
    // Restricted forms only:
    //   _* / ^*
    //   _{...} / ^{...}
    //   _(...) / ^(...)
    //
    // The inner text for bracketed forms is captured as raw script_text and
    // parsed into inline objects in the Python wrapper.
    subscript: $ => seq(
      '_',
      field('body', $._script_form),
    ),

    superscript: $ => seq(
      '^',
      field('body', $._script_form),
    ),

    _script_form: $ => choice(
      alias('*', $.script_text),
      seq('{', alias($._SCRIPT_BRACE_TEXT, $.script_text), '}'),
      seq('(', alias($._SCRIPT_PAREN_TEXT, $.script_text), ')'),
    ),

    _SCRIPT_BRACE_TEXT: _ => /[^{}\n]*/,
    _SCRIPT_PAREN_TEXT: _ => /[^()\n]*/,

    // --- 8.13 Plain Text ---
    // Plain text is handled by the external scanner to keep prev_char
    // tracking coherent for markup PRE/POST constraints.
    plain_text: $ => $._PLAIN_TEXT,

    // §9 Object Sets
    _object: $ => choice(
      $.export_snippet, $.footnote_reference, $.citation,
      $.inline_source_block, $.inline_babel_call, $.macro, $.line_break,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.completion_counter,
      $.entity,
      $.subscript, $.superscript,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    _object_nolb: $ => choice(
      $.export_snippet, $.footnote_reference, $.citation,
      $.inline_source_block, $.inline_babel_call, $.macro,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.completion_counter,
      $.entity,
      $.subscript, $.superscript,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    _object_nofn: $ => choice(
      $.export_snippet, $.citation,
      $.inline_source_block, $.inline_babel_call, $.macro, $.line_break,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.completion_counter,
      $.entity,
      $.subscript, $.superscript,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    _object_min: $ => choice(
      $.export_snippet, $.inline_source_block, $.inline_babel_call, $.macro, $.line_break,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.completion_counter,
      $.entity,
      $.subscript, $.superscript,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    _object_table: $ => choice(
      $.export_snippet, $.footnote_reference, $.citation,
      $.inline_source_block, $.inline_babel_call, $.macro,
      $.regular_link, $.angle_link, $.plain_link,
      $.target, $.radio_target, $.timestamp,
      $.completion_counter,
      $.entity,
      $.subscript, $.superscript,
      $.bold, $.italic, $.underline, $.strike_through,
      $.verbatim, $.code, $.plain_text,
    ),

    newline: $ => $._NL,
    blank_line: $ => $._blank_line,

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
