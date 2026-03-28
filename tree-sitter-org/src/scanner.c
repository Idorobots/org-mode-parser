/**
 * tree-sitter-org external scanner.
 *
 * Handles context-sensitive features that tree-sitter's grammar DSL
 * cannot express (syntax.md §12):
 *
 *   - Beginning-of-line detection (BOL via get_column)
 *   - Heading level tracking and containment
 *   - TODO keyword set management
 *   - Block begin/end name matching
 *   - Markup boundary lookbehind (PRE/POST constraints)
 *   - Paragraph termination
 *   - Footnote definition termination
 *   - Item tag ' :: ' detection
 *   - Plain text scanning to next object boundary
 */

#include "tree_sitter/parser.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

// ---------------------------------------------------------------------------
// External token enum — must match the order in grammar.js `externals`
// ---------------------------------------------------------------------------
enum TokenType {
  TOKEN_STARS,
  TOKEN_HEADING_END,
  TOKEN_TODO_KW,
  TOKEN_COMMENT_TOKEN,
  TOKEN_BLOCK_END_MATCH,
  TOKEN_GBLOCK_NAME,
  TOKEN_MARKUP_OPEN_BOLD,
  TOKEN_MARKUP_CLOSE_BOLD,
  TOKEN_MARKUP_OPEN_ITALIC,
  TOKEN_MARKUP_CLOSE_ITALIC,
  TOKEN_MARKUP_OPEN_UNDERLINE,
  TOKEN_MARKUP_CLOSE_UNDERLINE,
  TOKEN_MARKUP_OPEN_STRIKE,
  TOKEN_MARKUP_CLOSE_STRIKE,
  TOKEN_MARKUP_OPEN_VERBATIM,
  TOKEN_MARKUP_CLOSE_VERBATIM,
  TOKEN_MARKUP_OPEN_CODE,
  TOKEN_MARKUP_CLOSE_CODE,
  TOKEN_PARAGRAPH_CONTINUE,
  TOKEN_INDENT_PARAGRAPH_CONTINUE,
  TOKEN_INDENT_LIST_ITEM_CONTINUE,
  TOKEN_INDENT_CONTENT_CONTINUE,
  TOKEN_FNDEF_END,
  TOKEN_PLAIN_TEXT,
  TOKEN_ITEM_TAG_END,
  TOKEN_INDENT_BEGIN,
  TOKEN_INDENT_END,
  TOKEN_PLAN_KW,
  TOKEN_DYNBLOCK_SYNC,
  TOKEN_TODO_SETUP_SYNC,
  TOKEN_AFFILIATED_SYNC,
  TOKEN_DRAWER_ENTER_SYNC,
  TOKEN_DRAWER_EXIT_SYNC,
  TOKEN_ERROR_SENTINEL,
  TOKEN_TABLE_START,   // zero-width gate emitted once at the start of each org_table
  TOKEN_TABLE_BREAK_SYNC, // zero-width sync emitted when current org_table must end
  TOKEN_FIXED_WIDTH_COLON, // consumes optional indent + ':' only at BOL context
  TOKEN_INLINE_BABEL_START, // consumes 'call_' when followed by a valid name-start char
  TOKEN_INLINE_SRC_START,   // consumes 'src_' when followed by a valid lang-start char
  TOKEN_INLINE_BABEL_OUTSIDE_HEADER_START, // consumes '[' before inline babel outside header
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
#define MAX_HEADING_DEPTH   64
#define MAX_SECTION_BLOCK_DEPTH 64
#define MAX_BLOCK_DEPTH     16
#define MAX_TODO_KEYWORDS   32
#define MAX_TODO_KW_LEN     32
#define MAX_BLOCK_NAME_LEN  64
#define SERIALIZE_BUF_SIZE  1024

// Lesser block names that are NOT valid greater block names
static const char *LESSER_BLOCK_NAMES[] = {
  "comment", "example", "export", "src", "verse",
};
#define NUM_LESSER_BLOCKS 5

// Default TODO keywords
static const char *DEFAULT_TODO_KWS[] = {"TODO", "DONE"};
#define NUM_DEFAULT_TODO_KWS 2

// ---------------------------------------------------------------------------
// Predicates
// ---------------------------------------------------------------------------

// Markup PRE characters (before opening marker)
static bool is_markup_pre(int32_t ch) {
  return ch == ' ' || ch == '\t' || ch == '-' || ch == '(' ||
         ch == '{' || ch == '\'' || ch == '"' || ch == 0;
}

// Markup POST characters (after closing marker)
static bool is_markup_post(int32_t ch) {
  return ch == ' ' || ch == '\t' || ch == '\n' || ch == '-' ||
          ch == '.' || ch == ',' || ch == ';' || ch == ':' ||
          ch == '!' || ch == '?' || ch == '\'' || ch == ')' ||
          ch == '}' || ch == '[' || ch == '"' || ch == '\\' ||
          ch == '|' ||
          ch == 0;
}

static bool is_markup_marker(int32_t ch) {
  return ch == '*' || ch == '/' || ch == '_' || ch == '+' ||
         ch == '=' || ch == '~';
}

static bool is_markup_open_pre_for_marker(int32_t prev, int32_t marker) {
  return is_markup_pre(prev) || (is_markup_marker(prev) && prev != marker);
}

static bool is_markup_post_for_marker(int32_t marker, int32_t ch) {
  if (is_markup_post(ch)) return true;
  if (is_markup_marker(ch) && ch != marker) {
    // Avoid treating path-like '/.../_name' as italic by disallowing '/'
    // closes immediately before '_' markup markers.
    if (marker == '/' && ch == '_') return false;
    return true;
  }
  return false;
}

// Character that could start an object or element (for plain_text scanning)
// This must be conservative: plain_text scanning stops at any character
// that might start an object, markup, element, or special syntax.
static bool is_special_char(int32_t ch) {
  return ch == '*' || ch == '/' || ch == '_' || ch == '+' ||
          ch == '=' || ch == '~' || ch == '^' || ch == '[' || ch == '<' ||
          ch == '\\' || ch == '@' ||
          ch == '#' || ch == ':' || ch == '|' || ch == '>' ||
          ch == ']' || ch == '{';
}

// ---------------------------------------------------------------------------
// Scanner state
// ---------------------------------------------------------------------------
typedef struct {
  // Heading level stack
  uint8_t heading_levels[MAX_HEADING_DEPTH];
  uint8_t heading_depth;

  // TODO keyword set
  char todo_keywords[MAX_TODO_KEYWORDS][MAX_TODO_KW_LEN];
  uint8_t num_todo_keywords;

  // Block name stack (for begin/end matching)
  char block_names[MAX_BLOCK_DEPTH][MAX_BLOCK_NAME_LEN];
  uint8_t block_depth;

  // Previous character (for markup lookbehind). 0 = BOL/SOF.
  int32_t prev_char;

  // Consecutive blank line counter
  uint8_t consecutive_blank_lines;

  // Last column observed at scanner entry.
  // Used to detect line transitions that happen entirely through grammar
  // tokens (for example list bullets), where the scanner is not called at
  // column 0 and would otherwise keep stale prev_char state.
  uint16_t last_column;

  // Whether an italic markup opener '/' has been emitted on the current line
  // and not yet closed. Parallel flags are tracked for the other markup
  // delimiters so stray closers in plain text (e.g. "(.+)") are not emitted
  // as close tokens.
  bool bold_open;
  bool italic_open;
  bool underline_open;
  bool strike_open;
  bool verbatim_open;
  bool code_open;

  // True while scanning the first line of a heading (after TOKEN_STARS).
  // Used to limit heading-tag suffix probing (":tag:") to heading lines.
  bool in_heading_line;

  // Table tracking: true while the parser is inside an org_table.
  // Used by scan_table_start to prevent starting a new org_table mid-table,
  // which would cause each row to parse as a separate org_table node.
  bool in_table;

  // Count of plain-text '[' characters consumed but not yet closed by a
  // plain-text ']'. This lets plain-text scanning span grammar-level objects
  // (for example [<<target>>]) without producing spurious parse errors.
  uint16_t plain_lbracket_depth;

  // Section-local indentation block stack.
  uint16_t section_block_indents[MAX_SECTION_BLOCK_DEPTH];
  uint8_t section_block_depth;

  // One-shot guard: after closing a block on an ``:end:`` marker, do not
  // immediately reopen a block at the same line start.
  bool suppress_block_begin_on_end_line;

  // Drawer nesting depth (custom/property/logbook).
  uint8_t drawer_depth;

  // True when we just left column 0 via grammar/internal tokens (for example,
  // list bullets). Used to detect list-item tag separators in first-line text.
  bool bol_shifted_by_grammar;
} Scanner;

// ---------------------------------------------------------------------------
// String helpers
// ---------------------------------------------------------------------------
static bool str_eq_ci(const char *a, const char *b) {
  while (*a && *b) {
    char ca = (*a >= 'A' && *a <= 'Z') ? *a + 32 : *a;
    char cb = (*b >= 'A' && *b <= 'Z') ? *b + 32 : *b;
    if (ca != cb) return false;
    a++;
    b++;
  }
  return *a == *b;
}

static bool is_lesser_block_name(const char *name) {
  for (int i = 0; i < NUM_LESSER_BLOCKS; i++) {
    if (str_eq_ci(name, LESSER_BLOCK_NAMES[i])) return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Lexer helpers
// ---------------------------------------------------------------------------
static inline int32_t lookahead(TSLexer *lexer) {
  return lexer->lookahead;
}

static inline void advance(TSLexer *lexer) {
  lexer->advance(lexer, false);
}

static inline void skip_ws(TSLexer *lexer) {
  lexer->advance(lexer, true);
}

static inline void mark_end(TSLexer *lexer) {
  lexer->mark_end(lexer);
}

static inline bool eof(TSLexer *lexer) {
  return lexer->eof(lexer);
}

static inline uint32_t get_column(TSLexer *lexer) {
  return lexer->get_column(lexer);
}

static inline bool is_ascii_upper(int32_t ch) {
  return ch >= 'A' && ch <= 'Z';
}

static inline bool is_todo_keyword_char(int32_t ch) {
  return is_ascii_upper(ch) || ch == '-' || ch == '_';
}

static inline bool is_fixed_width_tail_char(int32_t ch, bool at_eof) {
  return ch == ' ' || ch == '\n' || at_eof;
}

static inline bool can_start_inline_hyphen_text(const Scanner *s, uint32_t col) {
  if (col == 0) return false;
  if (s->prev_char == 0) return false;

  // Keep grammar-level handling for constructs that use '-' after these
  // delimiters (table rule rows after '|', timestamp ranges after ']').
  if (s->prev_char == '|' || s->prev_char == ']' || s->prev_char == '>') {
    return false;
  }

  return true;
}

static bool scan_single_inline_hyphen(TSLexer *lexer) {
  advance(lexer);

  // Leave double-hyphen constructs to grammar-level rules (timestamp ranges,
  // table rule rows, etc.). Returning false after advance is safe: the caller
  // returns false to tree-sitter, which rewinds lexer position.
  if (lookahead(lexer) == '-') {
    // Preserve GNU-style switches (e.g. --watch, --serve) as plain text by
    // allowing a single leading '-' token when a double dash is followed by
    // an alphabetic character.
    mark_end(lexer);
    advance(lexer);
    int32_t next = lookahead(lexer);
    if (is_ascii_upper(next) || (next >= 'a' && next <= 'z')) return true;
    return false;
  }

  mark_end(lexer);
  return true;
}

static bool scanner_add_todo_keyword(Scanner *s, const char *kw) {
  if (kw == NULL || kw[0] == '\0') return false;

  for (uint8_t i = 0; i < s->num_todo_keywords; i++) {
    if (strcmp(s->todo_keywords[i], kw) == 0) return true;
  }

  if (s->num_todo_keywords >= MAX_TODO_KEYWORDS) return false;

  strncpy(s->todo_keywords[s->num_todo_keywords], kw, MAX_TODO_KW_LEN - 1);
  s->todo_keywords[s->num_todo_keywords][MAX_TODO_KW_LEN - 1] = '\0';
  s->num_todo_keywords++;
  return true;
}

static inline void reset_markup_open_state(Scanner *s) {
  s->bold_open = false;
  s->italic_open = false;
  s->underline_open = false;
  s->strike_open = false;
  s->verbatim_open = false;
  s->code_open = false;
}

static inline bool is_marker_open(const Scanner *s, int32_t marker) {
  switch (marker) {
    case '*': return s->bold_open;
    case '/': return s->italic_open;
    case '_': return s->underline_open;
    case '+': return s->strike_open;
    case '=': return s->verbatim_open;
    case '~': return s->code_open;
    default: return false;
  }
}

static inline void set_marker_open(Scanner *s, int32_t marker, bool open) {
  switch (marker) {
    case '*': s->bold_open = open; break;
    case '/': s->italic_open = open; break;
    case '_': s->underline_open = open; break;
    case '+': s->strike_open = open; break;
    case '=': s->verbatim_open = open; break;
    case '~': s->code_open = open; break;
  }
}

static bool probe_markup_close_in_rest_of_line(
    TSLexer *lexer,
    int32_t marker,
    int32_t *last_consumed_char,
    bool stop_before_right_bracket
);

// ---------------------------------------------------------------------------
// Scanner lifecycle
// ---------------------------------------------------------------------------

void *tree_sitter_org_external_scanner_create(void) {
  Scanner *scanner = calloc(1, sizeof(Scanner));
  if (scanner) {
    for (int i = 0; i < NUM_DEFAULT_TODO_KWS; i++) {
      strncpy(scanner->todo_keywords[i], DEFAULT_TODO_KWS[i], MAX_TODO_KW_LEN - 1);
    }
    scanner->num_todo_keywords = NUM_DEFAULT_TODO_KWS;
    scanner->prev_char = 0;
    scanner->last_column = 0;
    scanner->plain_lbracket_depth = 0;
    scanner->suppress_block_begin_on_end_line = false;
    scanner->drawer_depth = 0;
    scanner->bol_shifted_by_grammar = false;
    reset_markup_open_state(scanner);
  }
  return scanner;
}

void tree_sitter_org_external_scanner_destroy(void *payload) {
  free(payload);
}

// ---------------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------------

unsigned tree_sitter_org_external_scanner_serialize(
    void *payload,
    char *buffer
) {
  Scanner *s = (Scanner *)payload;
  unsigned pos = 0;

  // heading_depth + levels
  if (pos + 1 + s->heading_depth > SERIALIZE_BUF_SIZE) return 0;
  buffer[pos++] = (char)s->heading_depth;
  for (uint8_t i = 0; i < s->heading_depth; i++) {
    buffer[pos++] = (char)s->heading_levels[i];
  }

  // section_block_depth + indents (2 bytes each)
  if (pos + 1 + s->section_block_depth * 2 > SERIALIZE_BUF_SIZE) return 0;
  buffer[pos++] = (char)s->section_block_depth;
  for (uint8_t i = 0; i < s->section_block_depth; i++) {
    buffer[pos++] = (char)(s->section_block_indents[i] >> 8);
    buffer[pos++] = (char)(s->section_block_indents[i] & 0xFF);
  }

  // num_todo_keywords + keywords
  if (pos + 1 > SERIALIZE_BUF_SIZE) return 0;
  buffer[pos++] = (char)s->num_todo_keywords;
  for (uint8_t i = 0; i < s->num_todo_keywords; i++) {
    uint8_t len = (uint8_t)strlen(s->todo_keywords[i]);
    if (pos + 1 + len > SERIALIZE_BUF_SIZE) return 0;
    buffer[pos++] = (char)len;
    memcpy(&buffer[pos], s->todo_keywords[i], len);
    pos += len;
  }

  // block_depth + names
  if (pos + 1 > SERIALIZE_BUF_SIZE) return 0;
  buffer[pos++] = (char)s->block_depth;
  for (uint8_t i = 0; i < s->block_depth; i++) {
    uint8_t len = (uint8_t)strlen(s->block_names[i]);
    if (pos + 1 + len > SERIALIZE_BUF_SIZE) return 0;
    buffer[pos++] = (char)len;
    memcpy(&buffer[pos], s->block_names[i], len);
    pos += len;
  }

  // prev_char, consecutive_blank_lines, in_table, last_column,
  // plain_lbracket_depth,
  // markup-open flags, in_heading_line, suppress_block_begin_on_end_line,
  // drawer_depth, bol_shifted_by_grammar
  if (pos + 20 > SERIALIZE_BUF_SIZE) return 0;
  buffer[pos++] = (char)((s->prev_char >> 24) & 0xFF);
  buffer[pos++] = (char)((s->prev_char >> 16) & 0xFF);
  buffer[pos++] = (char)((s->prev_char >> 8) & 0xFF);
  buffer[pos++] = (char)(s->prev_char & 0xFF);
  buffer[pos++] = (char)s->consecutive_blank_lines;
  buffer[pos++] = (char)(s->in_table ? 1 : 0);
  buffer[pos++] = (char)((s->last_column >> 8) & 0xFF);
  buffer[pos++] = (char)(s->last_column & 0xFF);
  buffer[pos++] = (char)((s->plain_lbracket_depth >> 8) & 0xFF);
  buffer[pos++] = (char)(s->plain_lbracket_depth & 0xFF);
  buffer[pos++] = (char)(s->bold_open ? 1 : 0);
  buffer[pos++] = (char)(s->italic_open ? 1 : 0);
  buffer[pos++] = (char)(s->underline_open ? 1 : 0);
  buffer[pos++] = (char)(s->strike_open ? 1 : 0);
  buffer[pos++] = (char)(s->verbatim_open ? 1 : 0);
  buffer[pos++] = (char)(s->code_open ? 1 : 0);
  buffer[pos++] = (char)(s->in_heading_line ? 1 : 0);
  buffer[pos++] = (char)(s->suppress_block_begin_on_end_line ? 1 : 0);
  buffer[pos++] = (char)s->drawer_depth;
  buffer[pos++] = (char)(s->bol_shifted_by_grammar ? 1 : 0);

  return pos;
}

void tree_sitter_org_external_scanner_deserialize(
    void *payload,
    const char *buffer,
    unsigned length
) {
  Scanner *s = (Scanner *)payload;

  // Reset to defaults
  s->heading_depth = 0;
  s->block_depth = 0;
  s->section_block_depth = 0;
  s->prev_char = 0;
  s->consecutive_blank_lines = 0;
  s->last_column = 0;
  s->plain_lbracket_depth = 0;
  s->in_heading_line = false;
  s->suppress_block_begin_on_end_line = false;
  s->drawer_depth = 0;
  s->bol_shifted_by_grammar = false;
  reset_markup_open_state(s);

  for (int i = 0; i < NUM_DEFAULT_TODO_KWS; i++) {
    strncpy(s->todo_keywords[i], DEFAULT_TODO_KWS[i], MAX_TODO_KW_LEN - 1);
  }
  s->num_todo_keywords = NUM_DEFAULT_TODO_KWS;

  if (length == 0) return;
  unsigned pos = 0;

  // heading_depth + levels
  if (pos >= length) return;
  s->heading_depth = (uint8_t)buffer[pos++];
  for (uint8_t i = 0; i < s->heading_depth && pos < length; i++) {
    s->heading_levels[i] = (uint8_t)buffer[pos++];
  }

  // section_block_depth + indents
  if (pos >= length) return;
  s->section_block_depth = (uint8_t)buffer[pos++];
  for (uint8_t i = 0; i < s->section_block_depth && pos + 1 < length; i++) {
    s->section_block_indents[i] = (uint16_t)((uint8_t)buffer[pos] << 8 | (uint8_t)buffer[pos + 1]);
    pos += 2;
  }

  // num_todo_keywords + keywords
  if (pos >= length) return;
  s->num_todo_keywords = (uint8_t)buffer[pos++];
  for (uint8_t i = 0; i < s->num_todo_keywords && pos < length; i++) {
    uint8_t len = (uint8_t)buffer[pos++];
    if (pos + len > length) break;
    memcpy(s->todo_keywords[i], &buffer[pos], len);
    s->todo_keywords[i][len] = '\0';
    pos += len;
  }

  // block_depth + names
  if (pos >= length) return;
  s->block_depth = (uint8_t)buffer[pos++];
  for (uint8_t i = 0; i < s->block_depth && pos < length; i++) {
    uint8_t len = (uint8_t)buffer[pos++];
    if (pos + len > length) break;
    memcpy(s->block_names[i], &buffer[pos], len);
    s->block_names[i][len] = '\0';
    pos += len;
  }

  // prev_char, consecutive_blank_lines, in_table, last_column,
  // plain_lbracket_depth,
  // markup-open flags, in_heading_line, suppress_block_begin_on_end_line,
  // drawer_depth, bol_shifted_by_grammar
  if (pos + 5 <= length) {
    s->prev_char = ((int32_t)(uint8_t)buffer[pos] << 24) |
                   ((int32_t)(uint8_t)buffer[pos + 1] << 16) |
                   ((int32_t)(uint8_t)buffer[pos + 2] << 8) |
                   ((int32_t)(uint8_t)buffer[pos + 3]);
    pos += 4;
    s->consecutive_blank_lines = (uint8_t)buffer[pos++];
  }
  if (pos < length) {
    s->in_table = (bool)buffer[pos++];
  }
  if (pos + 1 < length) {
    s->last_column = (uint16_t)((uint8_t)buffer[pos] << 8 | (uint8_t)buffer[pos + 1]);
    pos += 2;
  }
  if (pos + 1 < length) {
    s->plain_lbracket_depth = (uint16_t)((uint8_t)buffer[pos] << 8 | (uint8_t)buffer[pos + 1]);
    pos += 2;
  }
  if (pos < length) {
    s->bold_open = (bool)buffer[pos++];
  }
  if (pos < length) {
    s->italic_open = (bool)buffer[pos++];
  }
  if (pos < length) {
    s->underline_open = (bool)buffer[pos++];
  }
  if (pos < length) {
    s->strike_open = (bool)buffer[pos++];
  }
  if (pos < length) {
    s->verbatim_open = (bool)buffer[pos++];
  }
  if (pos < length) {
    s->code_open = (bool)buffer[pos++];
  }
  if (pos < length) {
    s->in_heading_line = (bool)buffer[pos++];
  }
  if (pos < length) {
    s->suppress_block_begin_on_end_line = (bool)buffer[pos++];
  }
  if (pos < length) {
    s->drawer_depth = (uint8_t)buffer[pos++];
  }
  if (pos < length) {
    s->bol_shifted_by_grammar = (bool)buffer[pos++];
  }
}

// ---------------------------------------------------------------------------
// Token scan handlers
// ---------------------------------------------------------------------------

// Combined stars/heading_end scanner.
// At column 0 with '*'+ followed by space:
//   - If inside a heading and new level <= current level: emit _HEADING_END (zero-width)
//   - Otherwise: emit TOKEN_STARS and push the heading level
// At EOF inside a heading: emit _HEADING_END
//
// Strategy: We advance one char at a time, checking each successive char.
// If we advance past '*' and find the pattern is not a heading, we DON'T
// emit anything — we return false. The caller must handle the corrupted
// lexer state by trying to recover via TOKEN_PLAIN_TEXT.
//
// To avoid this complexity, we use a two-phase approach:
//   Phase 1: Advance past all '*', counting them
//   Phase 2: Check if followed by space
// If phase 2 fails, we've corrupted the lexer. The main scan function
// handles this by emitting TOKEN_PLAIN_TEXT as recovery.
// scan_heading_end_eof: emit _HEADING_END at EOF
static bool scan_heading_end_eof(Scanner *s, TSLexer *lexer) {
  if (!eof(lexer)) return false;
  if (s->heading_depth == 0) return false;
  lexer->result_symbol = TOKEN_HEADING_END;
  mark_end(lexer);
  s->heading_depth--;
  return true;
}

// Combined stars/heading_end scanner.
// At column 0 with '*'+ followed by space:
//   - If inside a heading and new level <= current level: emit _HEADING_END (zero-width)
//   - Otherwise: emit TOKEN_STARS and push the heading level
//
// If '*' at column 0 is NOT followed by space (not a heading), attempts to
// emit it as a markup open token (bold) if conditions are met.
//
// Returns: true if a token was emitted, false otherwise.
static bool scan_stars_or_heading_end(Scanner *s, TSLexer *lexer,
                                       const bool *valid_symbols) {
  if (get_column(lexer) != 0) return false;
  if (lookahead(lexer) != '*') return false;

  // Mark position before advancing (for zero-width _HEADING_END)
  mark_end(lexer);

  // Count and consume stars
  int count = 0;
  while (lookahead(lexer) == '*') {
    count++;
    advance(lexer);
  }

  int32_t after_stars = lookahead(lexer);

  // Stars must be followed by a space to be a heading
  if (count > 0 && (after_stars == ' ' || after_stars == '\t')) {
    // Valid heading pattern found. Decide: close existing heading or open new one.
    if (s->heading_depth > 0 && valid_symbols[TOKEN_HEADING_END]) {
      uint8_t current_level = s->heading_levels[s->heading_depth - 1];
      if ((uint8_t)count <= current_level) {
        // Same-or-higher-level heading: close current heading (zero-width token)
        lexer->result_symbol = TOKEN_HEADING_END;
        s->heading_depth--;
        return true;
      }
    }

    // Deeper-level heading or no heading to close: emit STARS
    if (valid_symbols[TOKEN_STARS]) {
      lexer->result_symbol = TOKEN_STARS;
      mark_end(lexer);

      if (s->heading_depth < MAX_HEADING_DEPTH) {
        s->heading_levels[s->heading_depth] = (uint8_t)count;
        s->heading_depth++;
      }
      s->in_heading_line = true;
      return true;
    }
    return false;
  }

  // NOT a heading. We've advanced past the '*'(s).
  // If exactly 1 star and the char after is not whitespace/newline/EOF,
  // this could be a markup bold open (*bold*).
  if (count == 1 && !eof(lexer) && after_stars != '\n' &&
      after_stars != ' ' && after_stars != '\t') {
    // Check PRE constraint: at column 0, prev_char is BOL (0) which is PRE
    if (valid_symbols[TOKEN_MARKUP_OPEN_BOLD]) {
      lexer->result_symbol = TOKEN_MARKUP_OPEN_BOLD;
      mark_end(lexer);
      s->prev_char = '*';
      s->bold_open = true;
      return true;
    }
  }

  // Multiple stars not followed by space, or no valid token to emit.
  // Recovery: emit consumed stars as plain text.
  if (valid_symbols[TOKEN_PLAIN_TEXT]) {
    // Continue consuming non-special chars as part of the plain text
    while (!eof(lexer) && lookahead(lexer) != '\n' && !is_special_char(lookahead(lexer))) {
      s->prev_char = lookahead(lexer);
      advance(lexer);
    }
    s->prev_char = '*';
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    mark_end(lexer);
    return true;
  }

  return false;
}

// _TODO_KW: match word against current TODO keyword set.
// If the consumed word is not a TODO keyword, emit plain_text fallback.
// For TitleCase words (e.g. "Fixed...") fail non-destructively so
// plain_text scanning can keep the title in one run.
static bool scan_todo_kw(Scanner *s, TSLexer *lexer, const bool *valid_symbols) {
  // TOKEN_TODO_KW is only valid inside a heading, always directly after the
  // stars have been scanned and $._S (the separating space) was consumed by
  // the grammar regex — which means prev_char was never updated to reflect
  // that space.  Set it now so that markup open scanners that run after us
  // (or after our PLAIN_TEXT fallback) see a correct PRE context.
  s->prev_char = ' ';

  char word[MAX_TODO_KW_LEN];
  int len = 0;

  // Mark position before consuming
  mark_end(lexer);

  while (is_todo_keyword_char(lookahead(lexer)) && len < MAX_TODO_KW_LEN - 1) {
    word[len++] = (char)lookahead(lexer);
    advance(lexer);
  }
  word[len] = '\0';

  if (len == 0) return false;

  // TODO keyword must be followed by space
  if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    for (uint8_t i = 0; i < s->num_todo_keywords; i++) {
      if (strcmp(word, s->todo_keywords[i]) == 0) {
        lexer->result_symbol = TOKEN_TODO_KW;
        mark_end(lexer);
        return true;
      }
    }
  }

  // If the uppercase run is immediately followed by lowercase text, this is
  // likely a normal title word (e.g. "Fixed...") rather than a TODO keyword.
  // Fail non-destructively so _PLAIN_TEXT can scan it as one run.
  if (lookahead(lexer) >= 'a' && lookahead(lexer) <= 'z') {
    return false;
  }

  // 'COMMENT' is the org-mode heading comment indicator, not a TODO keyword.
  // Emit it only when followed by a word boundary; otherwise treat it as
  // plain title text (e.g. "COMMENT:Title").
  if (strcmp(word, "COMMENT") == 0 && valid_symbols[TOKEN_COMMENT_TOKEN]) {
    int32_t after = lookahead(lexer);
    if (!eof(lexer) && after != ' ' && after != '\t' && after != '\n') {
      return false;
    }
    while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      advance(lexer);
    }
    lexer->result_symbol = TOKEN_COMMENT_TOKEN;
    mark_end(lexer);
    return true;
  }

  // Not a TODO keyword but we consumed uppercase letters.
  // Emit as plain text to avoid corrupting lexer state.
  // Continue consuming plain text up to the next object boundary.
  // Special case: if a bracket sequence starts immediately after the unknown
  // uppercase token (e.g. "PREPRODUCTION [#B]"), treat the whole bracketed
  // segment as plain text too. This avoids mis-parsing it as heading priority
  // in the fallback path for unrecognized TODO-like words.
  bool continuation_ran = false;
  while (!eof(lexer) && lookahead(lexer) != '\n') {
    if (lookahead(lexer) == '[') {
      s->prev_char = lookahead(lexer);
      advance(lexer);
      continuation_ran = true;

      while (!eof(lexer) && lookahead(lexer) != '\n' && lookahead(lexer) != ']') {
        s->prev_char = lookahead(lexer);
        advance(lexer);
      }

      if (lookahead(lexer) == ']') {
        s->prev_char = lookahead(lexer);
        advance(lexer);
      }
      continue;
    }

    if (is_special_char(lookahead(lexer))) break;

    s->prev_char = lookahead(lexer);
    advance(lexer);
    continuation_ran = true;
  }
  if (valid_symbols[TOKEN_PLAIN_TEXT]) {
    if (!continuation_ran) {
      s->prev_char = word[len - 1];
    }
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    mark_end(lexer);
    return true;
  }

  return false;
}

// _COMMENT_TOKEN: match exactly 'COMMENT' followed by a word boundary
// (space, tab, newline, or EOF).  Sets prev_char = ' ' like scan_todo_kw so
// that markup-open scanners see the correct PRE context for the title content
// that follows.
static bool scan_comment_token(Scanner *s, TSLexer *lexer) {
  // The grammar's $._S before this position consumed a space but did not
  // update prev_char; set it now so subsequent markup scanners are correct.
  s->prev_char = ' ';

  const char *KW = "COMMENT";
  mark_end(lexer);  // reset point: return false rewinds to here
  for (int i = 0; i < 7; i++) {
    if (eof(lexer) || lookahead(lexer) != KW[i]) return false;
    advance(lexer);
  }
  // Must end at a word boundary
  int32_t after = lookahead(lexer);
  if (!eof(lexer) && after != ' ' && after != '\t' && after != '\n') {
    return false;
  }
  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    advance(lexer);
  }
  lexer->result_symbol = TOKEN_COMMENT_TOKEN;
  mark_end(lexer);
  return true;
}

// _GBLOCK_NAME: block name that is NOT a lesser block name
static bool scan_gblock_name(Scanner *s, TSLexer *lexer) {
  char name[MAX_BLOCK_NAME_LEN];
  int len = 0;

  while (lookahead(lexer) != ' ' && lookahead(lexer) != '\t' &&
         lookahead(lexer) != '\n' && !eof(lexer) && len < MAX_BLOCK_NAME_LEN - 1) {
    name[len++] = (char)lookahead(lexer);
    advance(lexer);
  }
  name[len] = '\0';

  if (len == 0) return false;
  if (is_lesser_block_name(name)) return false;

  if (s->block_depth < MAX_BLOCK_DEPTH) {
    strncpy(s->block_names[s->block_depth], name, MAX_BLOCK_NAME_LEN - 1);
    s->block_names[s->block_depth][MAX_BLOCK_NAME_LEN - 1] = '\0';
    s->block_depth++;
  }

  lexer->result_symbol = TOKEN_GBLOCK_NAME;
  mark_end(lexer);
  return true;
}

// _BLOCK_END_MATCH: verify #+end_ name matches #+begin_ name
static bool scan_block_end_match(Scanner *s, TSLexer *lexer) {
  if (s->block_depth == 0) return false;

  char name[MAX_BLOCK_NAME_LEN];
  int len = 0;

  while (lookahead(lexer) != ' ' && lookahead(lexer) != '\t' &&
         lookahead(lexer) != '\n' && !eof(lexer) && len < MAX_BLOCK_NAME_LEN - 1) {
    name[len++] = (char)lookahead(lexer);
    advance(lexer);
  }
  name[len] = '\0';

  if (len == 0) return false;

  if (str_eq_ci(name, s->block_names[s->block_depth - 1])) {
    s->block_depth--;
    lexer->result_symbol = TOKEN_BLOCK_END_MATCH;
    mark_end(lexer);
    return true;
  }

  return false;
}

static bool is_list_line_start_context(const Scanner *s, uint32_t col);

// Markup open scanner.
// Returns: 1=token emitted, 0=no match without advance, -1=advanced but no token
static int scan_markup_open(
    Scanner *s,
    TSLexer *lexer,
    int32_t marker,
    enum TokenType token,
    const bool *valid_symbols
) {
  uint32_t marker_col = get_column(lexer);

  if (!is_markup_open_pre_for_marker(s->prev_char, marker)) return 0;
  if (lookahead(lexer) != marker) return 0;

  advance(lexer);
  mark_end(lexer);

  int32_t next = lookahead(lexer);

  // Doubled markers like "==", "//", "**" are plain text in Org.
  if (next == marker) {
    if (valid_symbols[TOKEN_PLAIN_TEXT]) {
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->prev_char = marker;
      return 1;
    }
    return -1;
  }

  if (marker == '+' && (next == ' ' || next == '\t' || next == '-')) {
    if (!is_list_line_start_context(s, marker_col) && valid_symbols[TOKEN_PLAIN_TEXT]) {
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->prev_char = marker;
      return 1;
    }
    return -1;
  }

  // Treat '/' between two adjacent markup markers as plain text separator.
  // Example: ~INCR~/~INCRBYFLOAT~ should parse as code '/' code, not italic.
  if (marker == '/' && is_markup_marker(s->prev_char) && is_markup_marker(next) &&
      valid_symbols[TOKEN_PLAIN_TEXT]) {
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->prev_char = '/';
    return 1;
  }

  // '*' followed by space/tab at a line-start context is an unordered list
  // bullet, not the opening of bold markup.  Yield to the grammar's
  // unordered_bullet token rule so the list_item rule can match instead.
  if (marker == '*' && (next == ' ' || next == '\t') &&
      is_list_line_start_context(s, marker_col)) {
    return -1;  // yield to unordered_bullet
  }

  if (next == ' ' || next == '\t' || next == '\n' || eof(lexer)) {
    if (valid_symbols[TOKEN_PLAIN_TEXT]) {
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->prev_char = marker;
      return 1;
    }
    return -1;
  }

  mark_end(lexer);

  if (!probe_markup_close_in_rest_of_line(lexer, marker, NULL, false)) {
    if (valid_symbols[TOKEN_PLAIN_TEXT]) {
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->prev_char = marker;
      return 1;
    }
    return -1;
  }

  lexer->result_symbol = token;
  s->prev_char = marker;
  set_marker_open(s, marker, true);
  return 1;
}

// Markup close scanner.
// Returns: 1=token emitted, 0=no match without advance, -1=advanced but no token
static int scan_markup_close(Scanner *s, TSLexer *lexer, int32_t marker, enum TokenType token) {
  if (s->prev_char == 0 || s->prev_char == ' ' || s->prev_char == '\t' || s->prev_char == '\n') return 0;
  if (lookahead(lexer) != marker) return 0;
  if (!is_marker_open(s, marker)) return 0;

  advance(lexer);
  mark_end(lexer);

  int32_t next = lookahead(lexer);

  if (eof(lexer) || is_markup_post_for_marker(marker, next)) {
    lexer->result_symbol = token;
    s->prev_char = marker;
    set_marker_open(s, marker, false);
    return 1;
  }

  return -1;
}

static bool is_list_line_start_context(const Scanner *s, uint32_t col) {
  if (col == 0) return true;
  return s->prev_char == 0 && s->section_block_depth > 0;
}

// _FNDEF_END: only emit at EOF or double blank line
static bool scan_fndef_end(Scanner *s, TSLexer *lexer) {
  (void)s;
  if (eof(lexer)) {
    lexer->result_symbol = TOKEN_FNDEF_END;
    mark_end(lexer);
    return true;
  }
  return false;
}

// _ITEM_TAG_END: find ' :: '
static bool scan_item_tag_end(Scanner *s, TSLexer *lexer) {
  if (lookahead(lexer) == ' ') {
    advance(lexer);
    if (lookahead(lexer) == ':') {
      advance(lexer);
      if (lookahead(lexer) == ':') {
        advance(lexer);
        if (lookahead(lexer) == ' ') {
          advance(lexer);
          lexer->result_symbol = TOKEN_ITEM_TAG_END;
          mark_end(lexer);
          return true;
        }
      }
    }
  }

  if (lookahead(lexer) == ':' && s->prev_char == ' ') {
    advance(lexer);
    if (lookahead(lexer) == ':') {
      advance(lexer);
      if (lookahead(lexer) == ' ') {
        advance(lexer);
        lexer->result_symbol = TOKEN_ITEM_TAG_END;
        mark_end(lexer);
        return true;
      }
    }
  }

  return false;
}

// Characters that could start internal grammar tokens (elements/objects)
// and should NOT be consumed as plain text fallback.
static bool is_internal_token_start(int32_t ch) {
  return ch == '#' || ch == ':' || ch == '|' || ch == '[' ||
         ch == '<' || ch == '@' || ch == '\\' ||
         ch == '>' || ch == ']';
}

static bool is_heading_tag_char(int32_t ch) {
  return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
         (ch >= '0' && ch <= '9') || ch == '_' || ch == '@' ||
         ch == '#' || ch == '%';
}

// Probe for a heading tags suffix after consuming the leading ':'
// of a candidate tags block (e.g. ":tag1:tag2:").
//
// The probe is intentionally strict:
// - one or more non-empty tags made of heading-tag characters
// - each tag terminated by ':'
// - only optional trailing spaces/tabs before end-of-line/EOF
static bool probe_heading_tags_suffix_after_colon(TSLexer *lexer) {
  if (!is_heading_tag_char(lookahead(lexer))) return false;

  while (true) {
    while (is_heading_tag_char(lookahead(lexer))) {
      advance(lexer);
    }

    if (lookahead(lexer) != ':') return false;
    advance(lexer);

    if (is_heading_tag_char(lookahead(lexer))) {
      continue;
    }

    while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      advance(lexer);
    }

    return lookahead(lexer) == '\n' || eof(lexer);
  }
}

static bool is_ascii_alpha(int32_t ch) {
  return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z');
}

static bool is_ascii_digit(int32_t ch) {
  return ch >= '0' && ch <= '9';
}

static bool is_word_constituent(int32_t ch) {
  return is_ascii_alpha(ch) || is_ascii_digit(ch);
}

static bool is_plain_link_type_initial(int32_t ch) {
  return ch == 's' || ch == 'n' || ch == 'm' ||
         ch == 'h' || ch == 'f' || ch == 'e';
}

static bool is_plain_link_path_char(int32_t ch) {
  return ch != ' ' && ch != '\t' && ch != '\n' &&
         ch != '[' && ch != ']' && ch != '<' && ch != '>' &&
         ch != '(' && ch != ')' && ch != 0;
}

// Match a short literal at the current cursor and advance on matched chars.
//
// Returns true when the full literal matched. Returns false on the first
// mismatch, potentially after consuming a prefix. The caller decides whether
// to keep consumed chars as plain_text fallback.
static bool match_literal_and_advance(
  TSLexer *lexer,
  const char *literal,
  bool *consumed_any,
  int32_t *last_consumed
) {
  for (const char *p = literal; *p != '\0'; p++) {
    if (lookahead(lexer) != *p) return false;
    advance(lexer);
    *consumed_any = true;
    *last_consumed = *p;
  }

  return true;
}

// Match the remainder of a supported plain-link type after the first letter
// has already been consumed.
static bool match_plain_link_type_suffix(
  TSLexer *lexer,
  int32_t first,
  bool *consumed_any,
  int32_t *last_consumed
) {
  switch (first) {
    case 's':
      return match_literal_and_advance(lexer, "hell", consumed_any, last_consumed);
    case 'n':
      return match_literal_and_advance(lexer, "ews", consumed_any, last_consumed);
    case 'm':
      return match_literal_and_advance(lexer, "ailto", consumed_any, last_consumed);
    case 'e':
      return match_literal_and_advance(lexer, "lisp", consumed_any, last_consumed);
    case 'h':
      if (match_literal_and_advance(lexer, "ttp", consumed_any, last_consumed)) {
        if (lookahead(lexer) == 's') {
          advance(lexer);
          *consumed_any = true;
          *last_consumed = 's';
        }
        return true;
      }
      return match_literal_and_advance(lexer, "elp", consumed_any, last_consumed);
    case 'f':
      if (match_literal_and_advance(lexer, "tp", consumed_any, last_consumed)) {
        return true;
      }
      return match_literal_and_advance(lexer, "ile", consumed_any, last_consumed);
    default:
      return false;
  }
}

// Probe and consume a plain-link candidate starting at the current cursor.
//
// Returns true if at least one character was consumed. `*matched` is set when
// the consumed run satisfies plain-link shape and word-post boundary:
//   LINK_TYPE ':' PATH  where PATH has at least one char.
//
// On failure, consumed characters are left consumed so the caller can keep
// them as plain_text. Callers rely on tree-sitter rewind behavior when they
// intentionally return false/break after a successful probe.
static bool scan_plain_link_candidate(TSLexer *lexer, bool *matched, int32_t *last_consumed) {
  *matched = false;
  *last_consumed = 0;

  int32_t ch = lookahead(lexer);
  if (!is_plain_link_type_initial(ch)) return false;

  bool consumed = false;

  // Parse one of the allowed lowercase link types.
  // shell, news, mailto, https, http, ftp, help, file, elisp
  advance(lexer);
  consumed = true;
  *last_consumed = ch;
  if (!match_plain_link_type_suffix(lexer, ch, &consumed, last_consumed)) {
    return consumed;
  }

  if (lookahead(lexer) != ':') return consumed;
  advance(lexer);
  *last_consumed = ':';

  if (!is_plain_link_path_char(lookahead(lexer))) return consumed;
  while (is_plain_link_path_char(lookahead(lexer))) {
    *last_consumed = lookahead(lexer);
    advance(lexer);
  }

  int32_t post = lookahead(lexer);
  if (post == '\n' || eof(lexer) || !is_word_constituent(post)) {
    *matched = true;
  }

  return consumed;
}

static bool is_angle_email_char(int32_t ch) {
  return is_ascii_alpha(ch) || is_ascii_digit(ch) ||
         ch == '.' || ch == '!' || ch == '#' || ch == '$' || ch == '%' ||
         ch == '&' || ch == '\'' || ch == '*' || ch == '+' || ch == '/' ||
         ch == '=' || ch == '?' || ch == '^' || ch == '_' || ch == '`' ||
         ch == '{' || ch == '|' || ch == '}' || ch == '~' || ch == '-';
}

static bool is_inline_babel_name_char(int32_t ch) {
  return ch != ' ' && ch != '\t' && ch != '\n' &&
         ch != '[' && ch != ']' && ch != '(' && ch != ')' &&
         ch != 0;
}

static bool is_inline_src_lang_char(int32_t ch) {
  return ch != ' ' && ch != '\t' && ch != '\n' &&
         ch != '[' && ch != '{' && ch != 0;
}

static bool consume_bracket_group_on_line(TSLexer *lexer, int32_t *last_consumed) {
  if (lookahead(lexer) != '[') return false;
  *last_consumed = '[';
  advance(lexer);

  while (!eof(lexer) && lookahead(lexer) != '\n') {
    int32_t ch = lookahead(lexer);
    *last_consumed = ch;
    advance(lexer);
    if (ch == ']') return true;
  }

  return false;
}

static bool consume_paren_group_on_line(TSLexer *lexer, int32_t *last_consumed) {
  if (lookahead(lexer) != '(') return false;
  *last_consumed = '(';
  advance(lexer);

  while (!eof(lexer) && lookahead(lexer) != '\n') {
    int32_t ch = lookahead(lexer);
    *last_consumed = ch;
    advance(lexer);
    if (ch == ')') return true;
  }

  return false;
}

static bool consume_brace_group_on_line(TSLexer *lexer, int32_t *last_consumed) {
  if (lookahead(lexer) != '{') return false;
  *last_consumed = '{';
  advance(lexer);

  while (!eof(lexer) && lookahead(lexer) != '\n') {
    int32_t ch = lookahead(lexer);
    *last_consumed = ch;
    advance(lexer);
    if (ch == '}') return true;
  }

  return false;
}

static bool probe_inline_babel_after_prefix(TSLexer *lexer, int32_t *last_consumed) {
  int32_t ch = lookahead(lexer);
  if (!is_inline_babel_name_char(ch)) return false;

  while (is_inline_babel_name_char(lookahead(lexer))) {
    ch = lookahead(lexer);
    *last_consumed = ch;
    advance(lexer);
  }

  if (lookahead(lexer) == '[') {
    if (!consume_bracket_group_on_line(lexer, last_consumed)) return false;
  }

  if (!consume_paren_group_on_line(lexer, last_consumed)) return false;

  if (lookahead(lexer) == '[') {
    if (!consume_bracket_group_on_line(lexer, last_consumed)) return false;
  }

  return true;
}

static bool probe_inline_src_after_prefix(TSLexer *lexer, int32_t *last_consumed) {
  int32_t ch = lookahead(lexer);
  if (!is_inline_src_lang_char(ch)) return false;

  while (is_inline_src_lang_char(lookahead(lexer))) {
    ch = lookahead(lexer);
    *last_consumed = ch;
    advance(lexer);
  }

  if (lookahead(lexer) == '[') {
    if (!consume_bracket_group_on_line(lexer, last_consumed)) return false;
  }

  if (!consume_brace_group_on_line(lexer, last_consumed)) return false;

  return true;
}

static bool probe_date_like_then_closing(TSLexer *lexer, int32_t closing) {
  for (int i = 0; i < 4; i++) {
    if (!is_ascii_digit(lookahead(lexer))) return false;
    advance(lexer);
  }
  if (lookahead(lexer) != '-') return false;
  advance(lexer);
  for (int i = 0; i < 2; i++) {
    if (!is_ascii_digit(lookahead(lexer))) return false;
    advance(lexer);
  }
  if (lookahead(lexer) != '-') return false;
  advance(lexer);
  for (int i = 0; i < 2; i++) {
    if (!is_ascii_digit(lookahead(lexer))) return false;
    advance(lexer);
  }

  while (!eof(lexer) && lookahead(lexer) != '\n') {
    if (lookahead(lexer) == closing) return true;
    advance(lexer);
  }

  return false;
}

static bool probe_angle_construct_after_lt(TSLexer *lexer) {
  if (lookahead(lexer) == '<') {
    // Treat bitshift-like text ("<< 2") as plain text, not a target opener.
    advance(lexer);
    int32_t next = lookahead(lexer);
    if (next == ' ' || next == '\t' || next == '\n' || eof(lexer)) return false;
    return true;  // target/radio_target opener
  }

  if (is_ascii_digit(lookahead(lexer))) {
    return probe_date_like_then_closing(lexer, '>');
  }

  if (!is_ascii_alpha(lookahead(lexer))) return false;
  while (is_ascii_alpha(lookahead(lexer))) {
    advance(lexer);
  }

  if (lookahead(lexer) == ':') return true;

  bool seen_at = false;
  bool seen_dot_after_at = false;
  while (!eof(lexer) && lookahead(lexer) != '\n' && lookahead(lexer) != '>') {
    int32_t ch = lookahead(lexer);
    if (ch == '@') {
      if (seen_at) return false;
      seen_at = true;
      advance(lexer);
      continue;
    }

    if (!is_angle_email_char(ch)) return false;
    if (seen_at && ch == '.') seen_dot_after_at = true;
    advance(lexer);
  }

  return lookahead(lexer) == '>' && seen_at && seen_dot_after_at;
}

static bool probe_bracket_construct_after_lbracket(TSLexer *lexer) {
  if (lookahead(lexer) == '[') return true;  // regular_link opener

  // Statistics / completion cookies: [N/M], [/], [N%], [%]
  if (lookahead(lexer) == '/' || lookahead(lexer) == '%') {
    advance(lexer);
    return lookahead(lexer) == ']';
  }

  if (is_ascii_digit(lookahead(lexer))) {
    int digits = 0;
    while (is_ascii_digit(lookahead(lexer))) {
      advance(lexer);
      digits++;
    }

    if (lookahead(lexer) == '/') {
      advance(lexer);
      while (is_ascii_digit(lookahead(lexer))) {
        advance(lexer);
      }
      return lookahead(lexer) == ']';
    }

    if (lookahead(lexer) == '%') {
      advance(lexer);
      return lookahead(lexer) == ']';
    }

    // Timestamp-like bracket: [YYYY-MM-DD ...]
    if (digits == 4 && lookahead(lexer) == '-') {
      advance(lexer);
      for (int i = 0; i < 2; i++) {
        if (!is_ascii_digit(lookahead(lexer))) return false;
        advance(lexer);
      }
      if (lookahead(lexer) != '-') return false;
      advance(lexer);
      for (int i = 0; i < 2; i++) {
        if (!is_ascii_digit(lookahead(lexer))) return false;
        advance(lexer);
      }

      while (!eof(lexer) && lookahead(lexer) != '\n') {
        if (lookahead(lexer) == ']') return true;
        advance(lexer);
      }
    }

    return false;
  }

  // Ordered-list counter-set cookie at item start: [@5] / [@a]
  if (lookahead(lexer) == '@') {
    advance(lexer);

    if (is_ascii_digit(lookahead(lexer))) {
      while (is_ascii_digit(lookahead(lexer))) {
        advance(lexer);
      }
    } else if (lookahead(lexer) >= 'a' && lookahead(lexer) <= 'z') {
      advance(lexer);
    } else {
      return false;
    }

    if (lookahead(lexer) != ']') return false;
    advance(lexer);
    return lookahead(lexer) == ' ' || lookahead(lexer) == '\t';
  }

  // Footnotes: [fn:...]
  if (lookahead(lexer) == 'f' || lookahead(lexer) == 'F') {
    advance(lexer);
    if (lookahead(lexer) != 'n' && lookahead(lexer) != 'N') return false;
    advance(lexer);
    return lookahead(lexer) == ':';
  }

  // Citations: [cite...: ...]
  if (lookahead(lexer) == 'c' || lookahead(lexer) == 'C') {
    const char *kw = "cite";
    for (int i = 0; kw[i] != '\0'; i++) {
      int32_t ch = lookahead(lexer);
      if (((ch >= 'A' && ch <= 'Z') ? ch + 32 : ch) != kw[i]) return false;
      advance(lexer);
    }
    return lookahead(lexer) == ':' || lookahead(lexer) == '/';
  }

  // Heading priority marker: [#A]
  if (lookahead(lexer) == '#') return true;

  // Checkbox at item start: [ ] / [X] / [-]
  if (lookahead(lexer) == ' ' || lookahead(lexer) == 'X' || lookahead(lexer) == '-') {
    advance(lexer);
    if (lookahead(lexer) != ']') return false;
    advance(lexer);
    return lookahead(lexer) == ' ' || lookahead(lexer) == '\t';
  }

  return false;
}

// Probe from immediately after a markup opener to determine whether
// a valid closing marker exists before end-of-line.
//
// Returns true iff a close marker is found with valid POST constraints.
// Advances lexer while probing; callers should rely on mark_end() to
// control the actual consumed extent of the returned token.
static bool probe_markup_close_in_rest_of_line(
    TSLexer *lexer,
    int32_t marker,
    int32_t *last_consumed_char,
    bool stop_before_right_bracket
) {
  bool has_body = false;
  int32_t prev = marker;
  uint32_t probe_lbracket_depth = 0;

  if (last_consumed_char) *last_consumed_char = marker;

  while (!eof(lexer) && lookahead(lexer) != '\n') {
    int32_t ch = lookahead(lexer);
    if (stop_before_right_bracket && ch == ']') {
      if (marker == '~' && probe_lbracket_depth > 0) {
        probe_lbracket_depth--;
      } else {
        return false;
      }
    }
    if (ch == '[') probe_lbracket_depth++;
    advance(lexer);
    if (last_consumed_char) *last_consumed_char = ch;

    if (ch == marker && has_body && prev != ' ' && prev != '\t' && prev != '\n' &&
        (eof(lexer) || is_markup_post_for_marker(marker, lookahead(lexer)))) {
      return true;
    }

    has_body = true;
    prev = ch;
  }

  return false;
}

// ---------------------------------------------------------------------------
// _INLINE_BABEL_START: consume 'call_' when followed by a valid name-start char.
//
// This external token replaces the literal 'call_' string in the
// inline_babel_call grammar rule.  Using an external token ensures that the
// scanner (not the GLR plain_text path) controls the token boundary: when
// TOKEN_PLAIN_TEXT and TOKEN_INLINE_BABEL_START are both valid, we emit the
// latter whenever 'call_' is followed by a valid function-name character,
// preventing plain_text from consuming the 'call_' prefix.
//
// s->prev_char is updated on every partial-match failure so that
// scan_plain_text (which runs next in the same scan() call) sees the correct
// lookbehind character when it decides whether markup delimiters can open or
// close.  Without this update the stale prev_char from before 'c' was
// consumed would cause incorrect markup detection for the first character
// after the partial match.
// ---------------------------------------------------------------------------
static bool scan_inline_babel_start(Scanner *s, TSLexer *lexer) {
  if (lookahead(lexer) != 'c') return false;
  int32_t last_consumed = 'c';
  advance(lexer);
  if (lookahead(lexer) != 'a') { s->prev_char = last_consumed; return false; }
  last_consumed = 'a';
  advance(lexer);
  if (lookahead(lexer) != 'l') { s->prev_char = last_consumed; return false; }
  last_consumed = 'l';
  advance(lexer);
  if (lookahead(lexer) != 'l') { s->prev_char = last_consumed; return false; }
  advance(lexer);
  if (lookahead(lexer) != '_') { s->prev_char = last_consumed; return false; }
  last_consumed = '_';
  advance(lexer);

  mark_end(lexer);

  if (!probe_inline_babel_after_prefix(lexer, &last_consumed)) {
    s->prev_char = last_consumed;
    return false;
  }

  lexer->result_symbol = TOKEN_INLINE_BABEL_START;
  return true;
}

// ---------------------------------------------------------------------------
// _INLINE_SRC_START: consume 'src_' when followed by a valid language-name start.
//
// Same rationale as _INLINE_BABEL_START but for inline_source_block.
// s->prev_char is updated on partial-match failure for the same reasons
// described above for scan_inline_babel_start.
// ---------------------------------------------------------------------------
static bool scan_inline_src_start(Scanner *s, TSLexer *lexer) {
  if (lookahead(lexer) != 's') return false;
  int32_t last_consumed = 's';
  advance(lexer);
  if (lookahead(lexer) != 'r') { s->prev_char = last_consumed; return false; }
  last_consumed = 'r';
  advance(lexer);
  if (lookahead(lexer) != 'c') { s->prev_char = last_consumed; return false; }
  last_consumed = 'c';
  advance(lexer);
  if (lookahead(lexer) != '_') { s->prev_char = last_consumed; return false; }
  last_consumed = '_';
  advance(lexer);

  mark_end(lexer);

  if (!probe_inline_src_after_prefix(lexer, &last_consumed)) {
    s->prev_char = last_consumed;
    return false;
  }

  lexer->result_symbol = TOKEN_INLINE_SRC_START;
  return true;
}

// ---------------------------------------------------------------------------
// _INLINE_BABEL_OUTSIDE_HEADER_START: consume '[' when the parser is in the
// optional inline babel outside-header suffix slot.
//
// This token exists only to beat TOKEN_PLAIN_TEXT at the `)[` boundary, so
// inline_babel_call can capture the trailing call_outside_header field.
// ---------------------------------------------------------------------------
static bool scan_inline_babel_outside_header_start(TSLexer *lexer) {
  if (lookahead(lexer) != '[') return false;
  advance(lexer);
  mark_end(lexer);
  lexer->result_symbol = TOKEN_INLINE_BABEL_OUTSIDE_HEADER_START;
  return true;
}

// _PLAIN_TEXT: scan forward to next object/element boundary
// Consumes "safe" characters that cannot start an object or element.
// If positioned at a markup character (*/_ +=~) that the markup scanner
// already rejected, consumes it as plain text to keep prev_char accurate.
static bool scan_plain_text(Scanner *s, TSLexer *lexer, const bool *valid_symbols,
                            bool prev_scanner_advanced) {
  // When scan_inline_babel_start or scan_inline_src_start ran before us in
  // the same scan() call, it may have consumed characters (e.g. 'c' or 's')
  // and returned false, leaving the lexer positioned past them.  If we are
  // now at '\n' or EOF, those already-consumed characters are part of the
  // current token.  Commit them as TOKEN_PLAIN_TEXT so they are not dropped.
  //
  // prev_scanner_advanced is true only when get_column() actually increased
  // during the babel/src scanner attempt, i.e. at least one advance() fired.
  // Using get_column() > 0 directly would be wrong: it reflects the document
  // column, which is non-zero any time the scanner is called mid-line — even
  // when no characters were consumed in this scan() call.  That would produce
  // zero-length TOKEN_PLAIN_TEXT tokens and cause an infinite parse loop.
  if (prev_scanner_advanced && (eof(lexer) || lookahead(lexer) == '\n')) {
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = 0;
    return true;
  }
  if (eof(lexer) || lookahead(lexer) == '\n') {
    return false;
  }

  if (s->drawer_depth == 0 && s->section_block_depth > 0 &&
      get_column(lexer) > 0 && lookahead(lexer) == ':') {
    advance(lexer);
    int32_t c2 = lookahead(lexer);
    if (c2 != 'e' && c2 != 'E') return false;
    advance(lexer);
    int32_t c3 = lookahead(lexer);
    if (c3 != 'n' && c3 != 'N') return false;
    advance(lexer);
    int32_t c4 = lookahead(lexer);
    if (c4 != 'd' && c4 != 'D') return false;
    advance(lexer);
    if (lookahead(lexer) != ':') return false;
    advance(lexer);
    s->prev_char = ':';
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = 0;
    return true;
  }

  if (get_column(lexer) == 0 &&
      (lookahead(lexer) == ' ' || lookahead(lexer) == '\t')) {
    return false;
  }

  if ((s->prev_char == '\n' || s->prev_char == 0) &&
      (lookahead(lexer) == ' ' || lookahead(lexer) == '\t')) {
    return false;
  }

  if (s->prev_char == 0 && get_column(lexer) > 0) {
    int32_t starter = lookahead(lexer);
    if (starter == '#' || starter == ':' || starter == '|' ||
        starter == '+' || starter == '*' ||
        starter == '[') {
      if (starter == ':' && s->drawer_depth == 0) {
        // Outside drawer context, allow malformed lone ":END:" lines to
        // degrade to plain text instead of forcing drawer dispatch.
      } else {
        return false;
      }
    }
  }

  // When we are at the first non-whitespace column of a line inside an
  // indentation block, keep ':' available for drawer/fixed-width element
  // dispatch instead of consuming it as plain text.
  if (s->drawer_depth > 0 && s->section_block_depth > 0 &&
      get_column(lexer) > 0 && lookahead(lexer) == ':') {
    return false;
  }

  bool found_any = false;
  bool bol_shifted = s->bol_shifted_by_grammar;
  uint32_t plain_lbracket_depth = s->plain_lbracket_depth;
  bool saw_plain_lbracket = plain_lbracket_depth > 0;
  bool maybe_clock_kw = (get_column(lexer) == 0 || s->prev_char == 0);
  int consumed_len = 0;

  while (!eof(lexer) && lookahead(lexer) != '\n') {
    int32_t ch = lookahead(lexer);

    // Keep the list-tag separator " :: " out of preceding plain_text so the
    // tag field does not inherit its leading separator space.
    if (ch == ' ' && found_any && bol_shifted && !s->in_heading_line) {
      int32_t last = ' ';
      advance(lexer);  // probe leading space
      if (lookahead(lexer) == ':') {
        last = ':';
        advance(lexer);  // probe first ':'
        if (lookahead(lexer) == ':') {
          advance(lexer);  // probe second ':'
          if (lookahead(lexer) == ' ') {
            break;
          }
          last = ':';
        }
      }

      s->prev_char = last;
      mark_end(lexer);
      found_any = true;
      continue;
    }

    // Detect plain links (type:path) with word-boundary guards so they are
    // parsed as plain_link objects instead of being swallowed by plain_text.
    //
    // _WORD_PRE: previous char is non-word or BOL
    // _WORD_POST: following char is non-word or EOL
    if (is_plain_link_type_initial(ch) &&
        (s->prev_char == 0 || !is_word_constituent(s->prev_char))) {
      bool plain_link_matched = false;
      int32_t last_plain_link_char = 0;
      bool consumed_plain_link_probe = scan_plain_link_candidate(
        lexer,
        &plain_link_matched,
        &last_plain_link_char
      );

      if (plain_link_matched) {
        if (!found_any) return false;
        break;
      }

      if (consumed_plain_link_probe) {
        // Keep inline source starts reachable when plain-link probing consumes
        // only the initial 's' and the actual text is a real `src_LANG{...}`
        // sequence. Do not split for unrelated `sr...` text (e.g. file paths
        // containing `/src/` or words like `shrug`).
        if (found_any && ch == 's' && last_plain_link_char == 's' &&
            lookahead(lexer) == 'r' && valid_symbols[TOKEN_INLINE_SRC_START]) {
          advance(lexer);  // consume 'r'
          if (lookahead(lexer) != 'c') {
            s->prev_char = 'r';
            mark_end(lexer);
            found_any = true;
            maybe_clock_kw = false;
            continue;
          }

          advance(lexer);  // consume 'c'
          if (lookahead(lexer) != '_') {
            s->prev_char = 'c';
            mark_end(lexer);
            found_any = true;
            maybe_clock_kw = false;
            continue;
          }

          advance(lexer);  // consume '_'
          int32_t probe_last = '_';
          if (probe_inline_src_after_prefix(lexer, &probe_last)) {
            break;
          }

          s->prev_char = probe_last;
          mark_end(lexer);
          found_any = true;
          maybe_clock_kw = false;
          continue;
        }
        s->prev_char = last_plain_link_char;
        mark_end(lexer);
        found_any = true;
        maybe_clock_kw = false;
        consumed_len++;
        continue;
      }
    }

    // ---------------------------------------------------------------------------
    // Alpha-bullet guard: when scan_inline_babel_start or scan_inline_src_start
    // ran first in this scan() call and consumed the BOL letter (column 0), the
    // lexer is now at column 1.  If the current character is '.' or ')' followed
    // by whitespace, this is the tail of an alpha-counter bullet ("c. text",
    // "s) text").  Yield to the grammar's _ordered_bullet rule — the same way
    // the explicit alpha-bullet check below does when starting at column 0.
    // ---------------------------------------------------------------------------
    if (!found_any && get_column(lexer) == 1 && (ch == '.' || ch == ')')) {
      advance(lexer);
      if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
        return false;  // yield to _ordered_bullet
      }
      // Not a bullet — include the consumed chars in the plain_text token.
      s->prev_char = ch;
      mark_end(lexer);
      found_any = true;
      continue;
    }

    if (!found_any && (get_column(lexer) == 0 || s->prev_char == 0) && is_ascii_digit(ch)) {
      int32_t last = ch;
      do {
        last = lookahead(lexer);
        advance(lexer);
      } while (is_ascii_digit(lookahead(lexer)));

      if (lookahead(lexer) == '.' || lookahead(lexer) == ')') {
        last = lookahead(lexer);
        advance(lexer);
        if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
          return false;
        }
      }

      s->prev_char = last;
      mark_end(lexer);
      found_any = true;
      continue;
    }

    // Avoid starting plain_text at [a-z][.)][ \t] at line start.  This yields
    // to the grammar's _ordered_bullet rule so single-letter alpha counters
    // (e.g. "a. item" / "b) item") are parsed as list_item, not paragraph.
    // The check mirrors the digit-ordered-bullet yield above: only fire when
    // no characters have been consumed yet and we are at a line-start position.
    if (!found_any && (get_column(lexer) == 0 || s->prev_char == 0) &&
        ch >= 'a' && ch <= 'z') {
      int32_t last = ch;
      advance(lexer);  // consume the letter
      int32_t next = lookahead(lexer);
      if (next == '.' || next == ')') {
        last = next;
        advance(lexer);  // consume the terminator
        if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
          return false;  // [a-z][.)][ \t] — yield to _ordered_bullet
        }
      }
      s->prev_char = last;
      mark_end(lexer);
      found_any = true;
      continue;
    }

    // Avoid starting a plain_text token at '-' in BOL contexts so grammar-level
    // constructs that begin with hyphen (table rule rows, list bullets, and
    // the plain '-' fallback token) can still match. Mid-line '-' should be
    // plain text, including after inline markup closers (e.g. "-_word_-").
    if (ch == '-' && !found_any) {
      if (get_column(lexer) == 0) {
        uint32_t run = 0;
        while (lookahead(lexer) == '-') {
          advance(lexer);
          run++;
        }

        int32_t next = lookahead(lexer);

        if (run >= 5) {
          return false;
        }

        if (run == 1 && (next == ' ' || next == '\t')) {
          return false;
        }

        s->prev_char = '-';
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (is_list_line_start_context(s, get_column(lexer))) {
        advance(lexer);
        if (lookahead(lexer) >= '0' && lookahead(lexer) <= '9') {
          s->prev_char = '-';
          mark_end(lexer);
          found_any = true;
          continue;
        }

        if (lookahead(lexer) == '\n' || eof(lexer)) {
          s->prev_char = '-';
          mark_end(lexer);
          found_any = true;
          continue;
        }

        return false;
      }

      if (s->prev_char == '>') {
        if (!scan_single_inline_hyphen(lexer)) return false;
        s->prev_char = ch;
        found_any = true;
        continue;
      }

      if (can_start_inline_hyphen_text(s, get_column(lexer))) {
        if (!scan_single_inline_hyphen(lexer)) return false;
        s->prev_char = ch;
        found_any = true;
        continue;
      }

      break;
    }

    // Keep inline hyphens attached to the current plain-text run.
    if (ch == '-' && found_any) {
      s->prev_char = ch;
      advance(lexer);
      mark_end(lexer);
      continue;
    }

    // Guard: when a previous scanner (scan_inline_babel_start or
    // scan_inline_src_start) consumed characters and we are now at a markup
    // delimiter as the very first character of this token, commit those
    // already-consumed characters as TOKEN_PLAIN_TEXT without including the
    // delimiter.  This prevents the markup-handling code below from firing
    // `!found_any → return false` (which would drop the consumed characters)
    // and allows the markup open/close scanners to handle the delimiter on
    // the very next scan() call.
    //
    // Example: inside /s/ (italic containing only 's'), scan_inline_src_start
    // consumes 's' and fails because '/' follows.  Without this guard,
    // scan_plain_text would see '/' as the first char, detect it as a viable
    // markup-close, and return false — leaving 's' uncommitted and causing a
    // parse error that cascades to an ERROR node for the enclosing paragraph.
    if (prev_scanner_advanced && !found_any && is_markup_marker(ch)) {
      mark_end(lexer);
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      // prev_char was already updated by the preceding scanner to the last
      // character it consumed, so no update is needed here.
      return true;
    }

    // Stop at characters that can start objects/elements, except when they
    // clearly do not form a valid construct and should remain plain text.
    if (is_special_char(ch)) {
      if (ch == '#') {
        // Keep line-start '#+' available for keyword/block parsing, including
        // indented starts where scanner context indicates BOL-like position.
        bool bol_like = is_list_line_start_context(s, get_column(lexer)) ||
                        (!found_any && s->prev_char == ' ');

        advance(lexer);
        if (!found_any && bol_like &&
            (lookahead(lexer) == '+' || lookahead(lexer) == ' ' ||
             lookahead(lexer) == '\n' || eof(lexer))) {
          return false;
        }

        s->prev_char = '#';
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (is_markup_marker(ch)) {
        bool can_close = false;
        bool can_open = false;
        uint32_t marker_col = get_column(lexer);
        int32_t prev_before_marker = s->prev_char;

        advance(lexer);

        if (ch == '+' && !found_any && marker_col == 0) {
          if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t' || lookahead(lexer) == '-') {
            return false;
          }
        }

        // Script candidate: x_*, x_{...}, x_(...).
        // Keep '_' available for grammar-level subscript parsing instead of
        // consuming it as plain text or underline marker.
        if (ch == '_' && prev_before_marker != ' ' && prev_before_marker != '\t' &&
            prev_before_marker != '\n' && prev_before_marker != 0 &&
            (lookahead(lexer) == '*' || lookahead(lexer) == '{' || lookahead(lexer) == '(')) {
          if (!found_any) return false;
          break;
        }

        if (s->prev_char != ' ' && s->prev_char != '\t' && s->prev_char != '\n' &&
            (eof(lexer) || is_markup_post_for_marker(ch, lookahead(lexer))) &&
            is_marker_open(s, ch)) {
          can_close = true;
        }

        // Avoid treating numeric suffixes like "3.21+ " as potential
        // strikethrough closes. This prevents false list/bullet recovery in
        // table cells and list item text while preserving real +strike+ cases.
        if (ch == '+' && (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') &&
            prev_before_marker >= '0' && prev_before_marker <= '9' &&
            !is_list_line_start_context(s, marker_col)) {
          can_close = false;
        }

        if (is_markup_open_pre_for_marker(s->prev_char, ch) && lookahead(lexer) != ' ' && lookahead(lexer) != '\t' &&
            lookahead(lexer) != '\n' && !eof(lexer)) {
          can_open = true;
        }

        // Doubled markers like "==", "//", "**" are plain text in Org.
        if (lookahead(lexer) == ch) {
          can_open = false;
        }

        // Keep common path fragments like "~/foo" as plain text instead of
        // treating '/' as a potential italic opener after '~'.
        if (ch == '/' && s->prev_char == '~') {
          can_open = false;
        }

        if (can_close && s->prev_char != 0) {
          if (!found_any) return false;
          break;
        }

        // Potential markup open boundary. If no closer exists on this line,
        // keep the remainder as plain text instead of creating missing-close
        // recovery nodes.
        if (can_open) {
          int32_t last = ch;
          if (probe_markup_close_in_rest_of_line(lexer, ch, &last, ch == '+' || ch == '~' || ch == '/' || ch == '*' || ch == '_')) {
            if (!found_any) return false;
            break;
          }

          s->prev_char = last;
          mark_end(lexer);
          found_any = true;
          continue;
        }

        // Marker is plain text here.
        s->prev_char = ch;
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (ch == ':') {
        if (bol_shifted && !s->in_heading_line && s->prev_char == ' ') {
          advance(lexer);  // probe first ':'
          if (lookahead(lexer) == ':') {
            advance(lexer);  // probe second ':'
            if (lookahead(lexer) == ' ') {
              if (!found_any) {
                if (valid_symbols[TOKEN_ITEM_TAG_END]) return false;
                s->prev_char = ':';
                mark_end(lexer);
                found_any = true;
                continue;
              }
              break;
            }
          }

          s->prev_char = ':';
          mark_end(lexer);
          found_any = true;
          continue;
        }

        // Preserve a leading CLOCK: token for the clock element rule.
        if (maybe_clock_kw && consumed_len == 5) {
          if (!found_any) return false;
          break;
        }

        // Preserve a real trailing heading tags suffix for grammar-level tags.
        // Inside list items, colon-wrapped tails (e.g. ":feature:") are text.
        if (s->in_heading_line && (s->prev_char == ' ' || s->prev_char == '\t')) {
          advance(lexer);
          if (is_heading_tag_char(lookahead(lexer)) && probe_heading_tags_suffix_after_colon(lexer)) {
            if (!found_any) return false;
            break;
          }

          s->prev_char = ':';
          mark_end(lexer);
          found_any = true;
          lexer->result_symbol = TOKEN_PLAIN_TEXT;
          s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
          return true;
        }

        s->prev_char = ':';
        advance(lexer);
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (ch == '|') {
        if (s->in_table) {
          if (!found_any) return false;
          break;
        }
        if (!found_any && get_column(lexer) == 0) return false;

        s->prev_char = '|';
        advance(lexer);
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (ch == '@') {
        advance(lexer);
        if (lookahead(lexer) == '@') {
          if (!found_any) return false;
          break;
        }

        s->prev_char = '@';
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (ch == '^') {
        advance(lexer);

        // Script candidate: x^*, x^{...}, x^(...).
        if (s->prev_char != ' ' && s->prev_char != '\t' && s->prev_char != '\n' &&
            s->prev_char != 0 &&
            (lookahead(lexer) == '*' || lookahead(lexer) == '{' || lookahead(lexer) == '(')) {
          if (!found_any) return false;
          break;
        }

        s->prev_char = '^';
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (ch == '>') {
        advance(lexer);
        if (lookahead(lexer) == '>') {
          if (!found_any) {
            bool likely_plain_gt_run =
              s->prev_char == '-' || s->prev_char == '>' || s->prev_char == ':' ||
              s->prev_char == '"' || s->prev_char == '\'' || s->prev_char == ')' ||
              s->prev_char == ',';
            if (likely_plain_gt_run) {
              s->prev_char = ch;
              mark_end(lexer);
              found_any = true;
              continue;
            }
            return false;
          }
          break;
        }

        s->prev_char = ch;
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (ch == ']') {
        advance(lexer);
        int32_t next = lookahead(lexer);
        if (s->prev_char == '\\') {
          s->prev_char = ch;
          mark_end(lexer);
          found_any = true;
          continue;
        }
        bool spaced_text = (s->prev_char == ' ' || s->prev_char == '\t') &&
          (next == ' ' || next == '\t' || next == '\n' || eof(lexer));
        bool lone_bol_text = get_column(lexer) == 1 && (next == '\n' || eof(lexer));

        // Preserve link/citation-style closing delimiters unless this closes
        // a plain-text '[' previously consumed in the current token.
        if (next == ']') {
          if (!saw_plain_lbracket) {
            plain_lbracket_depth = 0;
          }

          if (s->prev_char == '>') {
            if (!found_any) return false;
            break;
          }

          bool prefer_link_close_with_unmatched_plain_lbracket =
            saw_plain_lbracket &&
            ((plain_lbracket_depth == 1 && (s->prev_char == ',' || s->prev_char == '}')) ||
             (plain_lbracket_depth > 0 && s->prev_char == '['));

          if (prefer_link_close_with_unmatched_plain_lbracket) {
            if (!found_any) return false;
            break;
          }

          if (plain_lbracket_depth > 0 && saw_plain_lbracket) {
            plain_lbracket_depth--;
            s->prev_char = ch;
            mark_end(lexer);
            found_any = true;
            continue;
          }

          if (!found_any) return false;
          break;
        }

        bool trailing_after_bracket_close = (next == '\n' || eof(lexer)) &&
          (s->prev_char == ']' || s->prev_char == '}');
        bool bracket_ok = plain_lbracket_depth > 0 || saw_plain_lbracket || spaced_text || lone_bol_text ||
          next == ')' || next == '}' || next == ',' || trailing_after_bracket_close;
        if (!bracket_ok) {
          if (!found_any) return false;
          break;
        }

        if (plain_lbracket_depth > 0) {
          plain_lbracket_depth--;
        }

        s->prev_char = ch;
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (ch == '<' || ch == '[') {
        if (ch == '[' && s->prev_char == '\\') {
          s->prev_char = ch;
          advance(lexer);
          mark_end(lexer);
          found_any = true;
          continue;
        }

        advance(lexer);
        bool starts_object = (ch == '<')
          ? probe_angle_construct_after_lt(lexer)
          : probe_bracket_construct_after_lbracket(lexer);

        if (starts_object) {
          if (!found_any) return false;
          break;
        }

        if (ch == '[') {
          plain_lbracket_depth++;
          saw_plain_lbracket = true;
        }
        s->prev_char = ch;
        mark_end(lexer);
        found_any = true;
        continue;
      }

      if (ch == '\\') {
        advance(lexer);
        // Preserve Org hard line breaks ("\\") for grammar-level parsing.
        if (lookahead(lexer) == '\\') {
          advance(lexer);
          int32_t next = lookahead(lexer);
          bool hard_line_break = (next == ' ' || next == '\t' || next == '\n' || eof(lexer));
          if (hard_line_break) {
            if (!found_any) return false;
            break;
          }

          s->prev_char = '\\';
          mark_end(lexer);
          found_any = true;
          continue;
        }

        // Stop before \ALPHA — entity rule fires (e.g. \alpha, \Rightarrow).
        if (is_ascii_alpha(lookahead(lexer))) {
          if (!found_any) return false;
          break;
        }

        // Stop before \_SPACES — non-breaking-space entity (e.g. "\_ text").
        // Only stop when '_' is actually followed by whitespace; otherwise
        // consume '\' + '_' as plain text so "\_word" stays in plain text.
        if (lookahead(lexer) == '_') {
          advance(lexer);  // consume '_'
          int32_t after_us = lookahead(lexer);
          if (after_us == ' ' || after_us == '\t') {
            // Looks like \_ SPACES entity — stop so grammar rule fires.
            if (!found_any) return false;
            break;
          }
          // Not an entity — include '\' + '_' in the current plain-text run.
          s->prev_char = '_';
          mark_end(lexer);
          found_any = true;
          continue;
        }

        s->prev_char = ch;
        mark_end(lexer);
        found_any = true;
        continue;
      }

      // Stop plain_text before '{{{LETTER' which starts a macro.
      // Single '{' and '{{' that are not followed by a third '{' + letter
      // are consumed as plain text.
      if (ch == '{') {
        advance(lexer);                // consume first '{'
        if (lookahead(lexer) != '{') {
          // '{X' — include in plain text
          s->prev_char = '{';
          mark_end(lexer);
          found_any = true;
          continue;
        }
        advance(lexer);                // consume second '{'
        if (lookahead(lexer) != '{') {
          // '{{X' — include in plain text
          s->prev_char = '{';
          mark_end(lexer);
          found_any = true;
          continue;
        }
        advance(lexer);                // consume third '{'
        int32_t name_ch = lookahead(lexer);
        bool valid_macro_name_start =
          (name_ch >= 'A' && name_ch <= 'Z') || (name_ch >= 'a' && name_ch <= 'z');
        if (valid_macro_name_start) {
          // '{{{LETTER' — looks like a macro; stop here so the grammar rule fires.
          if (!found_any) return false;
          break;
        }
        // '{{{' not followed by a letter — include as plain text
        s->prev_char = '{';
        mark_end(lexer);
        found_any = true;
        continue;
      }

      break;
    }

    // ---------------------------------------------------------------------------
    // Stop plain_text before 'src_LANG' (inline_source_block start) so the
    // scanner's next call can emit TOKEN_INLINE_SRC_START instead.  Only probe
    // when TOKEN_INLINE_SRC_START is valid (we are in an _object context) AND
    // we already have prior text to emit (found_any).  The !found_any case is
    // handled by scan_inline_src_start being dispatched first in scan().
    // ---------------------------------------------------------------------------
    if (ch == 's' && found_any && valid_symbols[TOKEN_INLINE_SRC_START]) {
      advance(lexer);  // consume 's'
      if (lookahead(lexer) != 'r') {
        s->prev_char = 's'; mark_end(lexer); found_any = true; continue;
      }
      advance(lexer);  // consume 'r'
      if (lookahead(lexer) != 'c') {
        s->prev_char = 'r'; mark_end(lexer); found_any = true; continue;
      }
      advance(lexer);  // consume 'c'
      if (lookahead(lexer) != '_') {
        s->prev_char = 'c'; mark_end(lexer); found_any = true; continue;
      }
      advance(lexer);  // consume '_'
      int32_t lang_ch = lookahead(lexer);
      bool valid_lang_start = lang_ch != ' ' && lang_ch != '\t' && lang_ch != '\n' &&
                              lang_ch != '[' && lang_ch != '{' && !eof(lexer);
      if (valid_lang_start) {
        // Looks like 'src_LANG' — stop before 's' so _INLINE_SRC_START can fire.
        break;
      }
      // Not a valid start — include 'src_' in the token.
      s->prev_char = '_'; mark_end(lexer); found_any = true; continue;
    }

    // ---------------------------------------------------------------------------
    // Stop plain_text before 'call_NAME' (inline_babel_call start).  Same logic
    // as the 'src_' probe above: only fires when found_any is true.
    // ---------------------------------------------------------------------------
    if (ch == 'c' && found_any && valid_symbols[TOKEN_INLINE_BABEL_START]) {
      advance(lexer);  // consume 'c'
      if (lookahead(lexer) != 'a') {
        s->prev_char = 'c'; mark_end(lexer); found_any = true; continue;
      }
      advance(lexer);  // consume 'a'
      if (lookahead(lexer) != 'l') {
        s->prev_char = 'a'; mark_end(lexer); found_any = true; continue;
      }
      advance(lexer);  // consume first 'l'
      if (lookahead(lexer) != 'l') {
        s->prev_char = 'l'; mark_end(lexer); found_any = true; continue;
      }
      advance(lexer);  // consume second 'l'
      if (lookahead(lexer) != '_') {
        s->prev_char = 'l'; mark_end(lexer); found_any = true; continue;
      }
      advance(lexer);  // consume '_'
      int32_t name_ch = lookahead(lexer);
      bool valid_name_start = name_ch != ' ' && name_ch != '\t' && name_ch != '\n' &&
                              name_ch != '[' && name_ch != ']' &&
                              name_ch != '(' && name_ch != ')' && !eof(lexer);
      if (valid_name_start) {
        // Looks like 'call_NAME' — stop before 'c' so _INLINE_BABEL_START fires.
        break;
      }
      // Not a valid start — include 'call_' in the token.
      s->prev_char = '_'; mark_end(lexer); found_any = true; continue;
    }

    if (maybe_clock_kw) {
      static const char *kw = "CLOCK";
      if (consumed_len >= 5 || (ch | 32) != (kw[consumed_len] | 32)) {
        maybe_clock_kw = false;
      }
    }
    consumed_len++;

    s->prev_char = ch;
    advance(lexer);
    mark_end(lexer);
    found_any = true;
  }

  // Preserve a leading CLOCK: token for the clock element rule.
  if (found_any && lookahead(lexer) == ':' && maybe_clock_kw && consumed_len == 5) {
    return false;
  }

  // If we consumed some non-special chars, return them as plain text
  if (found_any) {
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  // We're at a special character. If it could start an internal grammar
  // token, do NOT consume it — the grammar needs a chance to try.
  // Only consume markup-related chars (*/_+=~) as single-char fallback,
  // since the markup open/close scanners already tried and failed.
  int32_t ch = lookahead(lexer);
  if (ch == '-') {
    if (s->prev_char == '>') {
      if (!scan_single_inline_hyphen(lexer)) return false;
      s->prev_char = ch;
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
      return true;
    }

    if (can_start_inline_hyphen_text(s, get_column(lexer))) {
      if (!scan_single_inline_hyphen(lexer)) return false;
      s->prev_char = ch;
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
      return true;
    }

    return false;
  }

  if (ch == ':') {
    // Mid-line colons are often plain text ("test ::", "value: text").
    // Treat ':' as potential heading-tags start only if the remainder is a
    // full tags suffix.
    if (s->in_heading_line && (s->prev_char == ' ' || s->prev_char == '\t')) {
      advance(lexer);
      s->prev_char = ':';
      mark_end(lexer);
      if (probe_heading_tags_suffix_after_colon(lexer)) {
        return false;
      }

      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
      return true;
    }

    s->prev_char = ':';
    advance(lexer);
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  if (ch == '|') {
    if (s->in_table) return false;
    if (get_column(lexer) == 0) return false;

    advance(lexer);
    s->prev_char = ch;
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  if (ch == '@') {
    advance(lexer);
    if (lookahead(lexer) == '@') return false;

    s->prev_char = '@';
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  if (ch == '>') {
    advance(lexer);
    if (lookahead(lexer) == '>') {
      bool likely_plain_gt_run =
        s->prev_char == '-' || s->prev_char == '>' || s->prev_char == ':' ||
        s->prev_char == '"' || s->prev_char == '\'' || s->prev_char == ')' ||
        s->prev_char == ',';
      if (!likely_plain_gt_run) return false;

      s->prev_char = ch;
      mark_end(lexer);
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
      return true;
    }

    s->prev_char = ch;
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  if (ch == ']') {
    advance(lexer);
    int32_t next = lookahead(lexer);
    if (s->prev_char == '\\') {
      s->prev_char = ch;
      mark_end(lexer);
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
      return true;
    }
    bool spaced_text = (s->prev_char == ' ' || s->prev_char == '\t') &&
      (next == ' ' || next == '\t' || next == '\n' || eof(lexer));
    bool lone_bol_text = get_column(lexer) == 1 && (next == '\n' || eof(lexer));

    if (next == ']') {
      if (!saw_plain_lbracket) {
        plain_lbracket_depth = 0;
      }

      if (s->prev_char == '>') return false;

      bool prefer_link_close_with_unmatched_plain_lbracket =
        saw_plain_lbracket &&
        ((plain_lbracket_depth == 1 && (s->prev_char == ',' || s->prev_char == '}')) ||
         (plain_lbracket_depth > 0 && s->prev_char == '['));

      if (prefer_link_close_with_unmatched_plain_lbracket) return false;

      if (plain_lbracket_depth > 0 && saw_plain_lbracket) {
        plain_lbracket_depth--;
        s->prev_char = ch;
        mark_end(lexer);
        lexer->result_symbol = TOKEN_PLAIN_TEXT;
        s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
        return true;
      }

      return false;
    }

    bool trailing_after_bracket_close = (next == '\n' || eof(lexer)) &&
      (s->prev_char == ']' || s->prev_char == '}');
    bool bracket_ok = plain_lbracket_depth > 0 || saw_plain_lbracket || spaced_text || lone_bol_text ||
      next == ')' || next == '}' || next == ',' || trailing_after_bracket_close;
    if (!bracket_ok) return false;

    if (plain_lbracket_depth > 0) {
      plain_lbracket_depth--;
    }

    s->prev_char = ch;
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  if (ch == '<' || ch == '[') {
    if (ch == '[' && s->prev_char == '\\') {
      s->prev_char = ch;
      advance(lexer);
      mark_end(lexer);
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
      return true;
    }

    advance(lexer);
    bool starts_object = (ch == '<')
      ? probe_angle_construct_after_lt(lexer)
      : probe_bracket_construct_after_lbracket(lexer);
    if (starts_object) return false;

    if (ch == '[') {
      plain_lbracket_depth++;
      saw_plain_lbracket = true;
    }

    s->prev_char = ch;
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  if (ch == '\\') {
    advance(lexer);
    if (lookahead(lexer) == '\\') {
      advance(lexer);
      int32_t next = lookahead(lexer);
      bool hard_line_break = (next == ' ' || next == '\t' || next == '\n' || eof(lexer));
      if (hard_line_break) return false;

      s->prev_char = '\\';
      mark_end(lexer);
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
      return true;
    }

    s->prev_char = ch;
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  if (!is_internal_token_start(ch)) {
    s->prev_char = ch;
    advance(lexer);
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    s->plain_lbracket_depth = (uint16_t)plain_lbracket_depth;
    return true;
  }

  return false;
}

// Helper to match a string literal at the current lexer position
static bool match_string(TSLexer *lexer, const char *str) {
  for (int i = 0; str[i] != '\0'; i++) {
    if (lookahead(lexer) != str[i]) return false;
    advance(lexer);
  }
  return true;
}

// _PLAN_KW: match DEADLINE, SCHEDULED, or CLOSED.
// On mismatch, fail without consuming input so other grammar tokens
// (e.g. CLOCK:) can be attempted at the same position.
static bool scan_plan_kw(Scanner *s, TSLexer *lexer, const bool *valid_symbols) {
  (void)s;
  (void)valid_symbols;
  int32_t ch = lookahead(lexer);
  const char *kw = NULL;

  if (ch == 'D') kw = "DEADLINE";
  else if (ch == 'S') kw = "SCHEDULED";
  else if (ch == 'C') kw = "CLOSED";
  else return false;

  // Do a lookahead-only match so failure does not consume input.
  for (int i = 0; kw[i] != '\0'; i++) {
    if (lookahead(lexer) != kw[i]) return false;
    advance(lexer);
  }

  lexer->result_symbol = TOKEN_PLAN_KW;
  mark_end(lexer);
  return true;
}

// _PARAGRAPH_CONTINUE
// Return values:
//   1  -> TOKEN_PARAGRAPH_CONTINUE emitted
//   0  -> no match, no advance performed
//  -1  -> no match after consuming indentation; caller must immediately
//         return false so tree-sitter rewinds before trying other tokens.
static int scan_paragraph_continue(TSLexer *lexer) {
  if (lookahead(lexer) != ' ' && lookahead(lexer) != '\t') return 0;

  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    advance(lexer);
  }

  mark_end(lexer);

  int32_t ch = lookahead(lexer);

  // Reject obvious element starters so indented lines parse as dedicated
  // constructs rather than paragraph continuations.
  if (ch == '*' || ch == '#' || ch == '|' || ch == ':' ||
      ch == '+' || ch == '-' || ch == '%' ||
      ch == 'C' || ch == 'D' || ch == 'S' ||
      ch == '\n' || (ch >= '0' && ch <= '9') || eof(lexer)) {
    return -1;
  }

  lexer->result_symbol = TOKEN_PARAGRAPH_CONTINUE;
  mark_end(lexer);
  return 1;
}

// _INDENT_PARAGRAPH_CONTINUE
// Return values:
//   1  -> TOKEN_INDENT_PARAGRAPH_CONTINUE emitted
//   0  -> no match, no advance performed
//  -1  -> no match after consuming indentation; caller must immediately
//         return false so tree-sitter rewinds before trying other tokens.
static int scan_block_paragraph_continue(Scanner *s, TSLexer *lexer) {
  if (s->section_block_depth == 0) return 0;
  if (lookahead(lexer) != ' ' && lookahead(lexer) != '\t') return 0;

  uint32_t indent_col = 0;
  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    indent_col++;
    advance(lexer);
  }

  mark_end(lexer);

  uint16_t current = s->section_block_indents[s->section_block_depth - 1];
  if (indent_col < current) return -1;

  int32_t ch = lookahead(lexer);
  if (ch == '*' || ch == '#' || ch == '|' || ch == ':' ||
      ch == '+' || ch == '-' || ch == '%' ||
      ch == 'C' || ch == 'D' || ch == 'S' ||
      ch == '\n' || (ch >= '0' && ch <= '9') || eof(lexer)) {
    return -1;
  }

  lexer->result_symbol = TOKEN_INDENT_PARAGRAPH_CONTINUE;
  return 1;
}

// Probe for list bullet syntax at current position.
// Return values:
//   1  -> matched list bullet prefix
//   0  -> no match, no advance performed
//  -1  -> no match after advance(s); caller must return false to rewind
static int scan_block_list_bullet_start(TSLexer *lexer) {
  uint32_t col_before = get_column(lexer);
  int32_t ch = lookahead(lexer);

  if (ch == '+' || ch == '-' || ch == '*') {
    advance(lexer);
    if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      return 1;
    }
    return -1;
  }

  if (ch >= '0' && ch <= '9') {
    do {
      advance(lexer);
      ch = lookahead(lexer);
    } while (ch >= '0' && ch <= '9');

    if (ch != '.' && ch != ')') return -1;
    advance(lexer);
    if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      return 1;
    }
    return -1;
  }

  if (ch >= 'a' && ch <= 'z') {
    advance(lexer);
    ch = lookahead(lexer);
    if (ch != '.' && ch != ')') return -1;
    advance(lexer);
    if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      return 1;
    }
    return -1;
  }

  return get_column(lexer) == col_before ? 0 : -1;
}

static bool starts_with_end_marker(TSLexer *lexer) {
  if (lookahead(lexer) != ':') return false;

  advance(lexer);
  int32_t c2 = lookahead(lexer);
  if (c2 != 'e' && c2 != 'E') return false;

  advance(lexer);
  int32_t c3 = lookahead(lexer);
  if (c3 != 'n' && c3 != 'N') return false;

  advance(lexer);
  int32_t c4 = lookahead(lexer);
  if (c4 != 'd' && c4 != 'D') return false;

  advance(lexer);
  return lookahead(lexer) == ':';
}

// _INDENT_CONTENT_CONTINUE fallback path for parser states where
// TOKEN_INDENT_END is not valid.
static int scan_block_content_continue(Scanner *s, TSLexer *lexer,
                                       const bool *valid_symbols) {
  if (s->section_block_depth == 0) return 0;
  if (lookahead(lexer) != ' ' && lookahead(lexer) != '\t') return 0;

  uint32_t indent_col = 0;
  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    indent_col++;
    advance(lexer);
  }

  mark_end(lexer);

  uint16_t current = s->section_block_indents[s->section_block_depth - 1];
  if (indent_col < current) return -1;

  int32_t ch = lookahead(lexer);
  if (ch == '\n' || eof(lexer)) return -1;

  if (indent_col > current && valid_symbols[TOKEN_INDENT_BEGIN]) return -1;

  if (s->drawer_depth > 0 && indent_col == current && ch == ':') {
    if (starts_with_end_marker(lexer)) return -1;
  }

  lexer->result_symbol = TOKEN_INDENT_CONTENT_CONTINUE;
  return 1;
}

// _INDENT_LIST_ITEM_CONTINUE fallback path for parser states where
// TOKEN_INDENT_END is not valid.
static int scan_block_list_item_continue(Scanner *s, TSLexer *lexer) {
  if (s->section_block_depth == 0) return 0;
  if (lookahead(lexer) != ' ' && lookahead(lexer) != '\t') return 0;

  uint32_t indent_col = 0;
  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    indent_col++;
    advance(lexer);
  }

  mark_end(lexer);

  uint16_t current = s->section_block_indents[s->section_block_depth - 1];
  if (indent_col != current) return -1;
  int probe = scan_block_list_bullet_start(lexer);
  if (probe != 1) return -1;

  lexer->result_symbol = TOKEN_INDENT_LIST_ITEM_CONTINUE;
  return 1;
}

// _INDENT_BEGIN: consume leading indentation that opens a section block.
static int scan_block_begin(Scanner *s, TSLexer *lexer, const bool *valid_symbols) {
  if (get_column(lexer) != 0) return 0;
  if (eof(lexer)) return 0;
  if (s->suppress_block_begin_on_end_line) return 0;

  int32_t ch = lookahead(lexer);
  if (ch != ' ' && ch != '\t') return 0;

  uint32_t indent_col = 0;
  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    indent_col++;
    advance(lexer);
  }

  // Heading planning lines consume their own optional indentation and should
  // not be wrapped as section blocks.
  if (valid_symbols[TOKEN_PLAN_KW]) {
    int32_t starter = lookahead(lexer);
    if (starter == 'D' || starter == 'S' || starter == 'C') {
      return -1;
    }
  }

  if (lookahead(lexer) == '\n' || eof(lexer)) return -1;

  int32_t starter = lookahead(lexer);

  uint16_t current = s->section_block_depth == 0
    ? 0
    : s->section_block_indents[s->section_block_depth - 1];

  if (indent_col == current) return -1;

  if (indent_col < current) {
    bool drawer_misaligned_continuation =
      s->drawer_depth > 0 &&
      indent_col > 0 &&
      starter != ':' &&
      starter != '+' &&
      starter != '-' &&
      starter != '*' &&
      starter != '#' &&
      starter != '|' &&
      starter != '%' &&
      !(starter >= '0' && starter <= '9');

    if (!drawer_misaligned_continuation) return -1;
  }
  if (s->section_block_depth >= MAX_SECTION_BLOCK_DEPTH) return -1;

  /* Fix the token boundary to the consumed whitespace now.  All advance()
   * calls below are purely for lookahead and do not extend the token.
   * State changes happen only after these checks succeed. */
  lexer->result_symbol = TOKEN_INDENT_BEGIN;
  mark_end(lexer);

  /* Don't open a block for ':end:' lines: after scan_block_end closes a
   * block via the :end:-detection path, we must not immediately re-open
   * one so that the enclosing drawer rule can match its terminator token. */
  if (s->drawer_depth > 0 && starter == ':') {
    advance(lexer);
    int32_t c2 = lookahead(lexer);
    if (c2 == 'e' || c2 == 'E') {
      advance(lexer);
      int32_t c3 = lookahead(lexer);
      if (c3 == 'n' || c3 == 'N') {
        advance(lexer);
        int32_t c4 = lookahead(lexer);
        if (c4 == 'd' || c4 == 'D') {
          advance(lexer);
          int32_t c5 = lookahead(lexer);
          if (c5 == ':') return -1;  /* no state modified yet — safe */
        }
      }
    }
  }

  s->section_block_indents[s->section_block_depth] = (uint16_t)indent_col;
  s->section_block_depth++;
  s->prev_char = 0;
  return 1;
}

// _INDENT_END: zero-width token to close active section blocks on dedent.
static int scan_block_end(Scanner *s, TSLexer *lexer, const bool *valid_symbols) {
  if (s->section_block_depth == 0) return 0;
  if (get_column(lexer) != 0) return 0;

  mark_end(lexer);

  uint32_t indent_col = 0;
  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    indent_col++;
    advance(lexer);
  }

  int32_t ch = lookahead(lexer);
  uint16_t current = s->section_block_indents[s->section_block_depth - 1];
  bool list_probe_advanced_miss = false;

  if (indent_col == current && valid_symbols[TOKEN_INDENT_LIST_ITEM_CONTINUE]) {
    mark_end(lexer);
    int probe = scan_block_list_bullet_start(lexer);
    if (probe == 1) {
      lexer->result_symbol = TOKEN_INDENT_LIST_ITEM_CONTINUE;
      return 1;
    }
    if (probe == -1) {
      list_probe_advanced_miss = true;
    }
  }

  if (indent_col == current && valid_symbols[TOKEN_INDENT_PARAGRAPH_CONTINUE]) {
    if (ch != '*' && ch != '#' && ch != '|' && ch != ':' &&
        ch != '+' && ch != '-' && ch != '%' &&
        ch != 'C' && ch != 'D' && ch != 'S' &&
        ch != '\n' && !(ch >= '0' && ch <= '9') && !eof(lexer)) {
      mark_end(lexer);
      lexer->result_symbol = TOKEN_INDENT_PARAGRAPH_CONTINUE;
      return 1;
    }
  }

  if (indent_col > current && !eof(lexer) && ch != '\n' &&
      !(s->drawer_depth > 0 && ch == ':') &&
      valid_symbols[TOKEN_INDENT_BEGIN]) {
    if (s->section_block_depth >= MAX_SECTION_BLOCK_DEPTH) return -1;
    s->section_block_indents[s->section_block_depth] = (uint16_t)indent_col;
    s->section_block_depth++;
    mark_end(lexer);
    lexer->result_symbol = TOKEN_INDENT_BEGIN;
    return 1;
  }

  bool should_close = false;
  bool close_on_end_marker = false;

  if (eof(lexer)) {
    should_close = true;
  } else if (indent_col < current) {
    bool drawer_misaligned_continuation =
      s->drawer_depth > 0 &&
      indent_col > 0 &&
      ch != ':' &&
      ch != '+' &&
      ch != '-' &&
      ch != '*' &&
      ch != '#' &&
      ch != '|' &&
      ch != '%' &&
      !(ch >= '0' && ch <= '9');

    if (drawer_misaligned_continuation) {
      should_close = false;
    } else {
      should_close = true;
    }
  } else if (s->drawer_depth > 0 && indent_col == current && ch == ':') {
    if (current <= 2) {
      mark_end(lexer);
    }

    /* Peek for ':end:' case-insensitively.  mark_end() was already called
     * above, so these advances do not extend the zero-width token boundary.
     * This handles drawer :END: markers at the same indentation level as
     * the block content (e.g. mis-aligned archive-style logbooks). */
    if (starts_with_end_marker(lexer)) {
      should_close = true;
      close_on_end_marker = true;
    }
  } else if (s->drawer_depth > 0 && indent_col > current && ch == ':') {
    should_close = true;
    close_on_end_marker = true;
  }

  if (!should_close) {
    if (valid_symbols[TOKEN_INDENT_CONTENT_CONTINUE] &&
        indent_col >= current && !eof(lexer) && ch != '\n') {
      if (!list_probe_advanced_miss) {
        mark_end(lexer);
      }
      lexer->result_symbol = TOKEN_INDENT_CONTENT_CONTINUE;
      return 1;
    }

    return -1;
  }

  s->section_block_depth--;
  s->suppress_block_begin_on_end_line = close_on_end_marker;
  lexer->result_symbol = TOKEN_INDENT_END;
  return 1;
}

// _TABLE_START: zero-width token emitted once at the start of each org_table.
//
// The scanner tracks `in_table` to prevent GLR from creating a separate
// org_table node for each row of a multi-row table.  When the parser is
// trying to open a new org_table (TOKEN_TABLE_START is in valid_symbols):
//
//   - If the next character is NOT '|': the table cannot start here; reset
//     in_table to false (this is how the flag is cleared when a table ends
//     and the parser returns to element level looking for the next element).
//
//   - If the next character IS '|' and in_table is false: emit _TABLE_START
//     and set in_table = true.
//
//   - If the next character IS '|' but in_table is already true: we are
//     already inside an org_table.  Return false so the parser cannot open
//     a second org_table for this row; GLR paths that try to do so are pruned.
//
// TOKEN_TABLE_START is only in valid_symbols when the grammar is at element
// level (the beginning of an org_table), never while parsing rows inside one,
// so this check fires in exactly the right contexts.
static int scan_table_start(Scanner *s, TSLexer *lexer) {
  mark_end(lexer);  // zero-width token

  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    advance(lexer);
  }

  int32_t ch = lookahead(lexer);
  if (ch != '|') {
    // Not the start of a table row.  Reset in_table so the next real table
    // (after a non-table element) can start normally.
    s->in_table = false;
    return 0;
  }

  if (s->in_table) {
    // Already inside a table; do not start a new one.  This kills any GLR
    // path that tries to reduce the current org_table early and open a fresh
    // one for the next row.
    return 0;
  }

  s->in_table = true;
  lexer->result_symbol = TOKEN_TABLE_START;
  return 1;
}

// _TABLE_BREAK_SYNC: zero-width sync point used to close org_table boundaries.
//
// This token is placed at the end of org_table in grammar.js. It emits only
// when the next non-whitespace character on the current line is NOT '|', which
// means the current table must end at this position.
//
// If the next non-whitespace character is '|', we are still in the same table
// and this token must not match (to prevent premature table reduction and
// split-table GLR paths).
static int scan_table_break_sync(Scanner *s, TSLexer *lexer) {
  mark_end(lexer);  // zero-width token
  bool advanced = false;

  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    advance(lexer);
    advanced = true;
  }

  int32_t ch = lookahead(lexer);

  if (ch == '|') return advanced ? -1 : 0;

  // Keep the table open at the beginning of a TBLFM line so `tblfm_line`
  // is consumed and attached to org_table.
  if (ch == '#') {
    const char *kw = "#+tblfm:";
    bool matches = true;

    for (int i = 0; kw[i] != '\0'; i++) {
      int32_t c = lookahead(lexer);
      if (eof(lexer)) {
        matches = false;
        break;
      }
      if (c >= 'A' && c <= 'Z') c = c + 32;
      if (c != kw[i]) {
        matches = false;
        break;
      }
      advance(lexer);
    }

    if (matches) return advanced ? -1 : 0;
  }

  s->in_table = false;
  lexer->result_symbol = TOKEN_TABLE_BREAK_SYNC;
  return 1;
}

// _DYNBLOCK_SYNC: zero-width sync point used at dynamic-block boundaries.
//
// Dynamic-block begin/end lines are internal regex tokens. Depending on parse
// path, the external scanner may not be invoked on those lines, which can let
// table state leak from one dynamic block into the next. Emitting this token
// where the grammar expects it guarantees a scanner callback and clears any
// stale table-open flag before parsing the closing marker / next block.
static bool scan_dynblock_sync(Scanner *s, TSLexer *lexer) {
  s->in_table = false;
  mark_end(lexer);
  lexer->result_symbol = TOKEN_DYNBLOCK_SYNC;
  return true;
}

// _AFFILIATED_SYNC: zero-width sync point used on affiliated-keyword lines.
//
// Affiliated keywords can appear between two tables. Depending on parse path,
// the scanner may not be consulted in a way that clears table state between
// them, causing the next table opener to be suppressed. Emitting this token in
// affiliated keyword rules guarantees a scanner callback and clears stale
// table-open state before the following element is parsed.
static bool scan_affiliated_sync(Scanner *s, TSLexer *lexer) {
  s->in_table = false;
  mark_end(lexer);
  lexer->result_symbol = TOKEN_AFFILIATED_SYNC;
  return true;
}

// _DRAWER_ENTER_SYNC: zero-width sync point used immediately after drawer
// opening lines. Keeps scanner state aligned with grammar-level drawer entry.
static bool scan_drawer_enter_sync(Scanner *s, TSLexer *lexer) {
  if (s->drawer_depth < UINT8_MAX) {
    s->drawer_depth++;
  }

  mark_end(lexer);
  lexer->result_symbol = TOKEN_DRAWER_ENTER_SYNC;
  return true;
}

// _DRAWER_EXIT_SYNC: zero-width sync point used immediately after drawer
// closing lines. Keeps scanner state aligned with grammar-level drawer exit.
static bool scan_drawer_exit_sync(Scanner *s, TSLexer *lexer) {
  if (s->drawer_depth > 0) {
    s->drawer_depth--;
  }

  mark_end(lexer);
  lexer->result_symbol = TOKEN_DRAWER_EXIT_SYNC;
  return true;
}

// _TODO_SETUP_SYNC: zero-width sync point used on special_keyword lines.
//
// When positioned at a line that begins with "#+TODO:", parse the remainder
// of the line and add discovered TODO keywords to scanner state. Supported:
//   - plain words: TODO, DONE, SUSPENDED
//   - separator: |
//   - keywords with controls: DONE(d@/!) -> DONE
//
// Keywords are accumulated across multiple #+TODO lines; existing defaults are
// preserved and never replaced.
static bool scan_todo_setup_sync(Scanner *s, TSLexer *lexer) {
  mark_end(lexer);

  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    advance(lexer);
  }

  while (!eof(lexer) && lookahead(lexer) != '\n') {
    while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      advance(lexer);
    }
    if (eof(lexer) || lookahead(lexer) == '\n') break;

    char token[MAX_TODO_KW_LEN];
    int token_len = 0;
    while (!eof(lexer) && lookahead(lexer) != '\n' && lookahead(lexer) != ' ' && lookahead(lexer) != '\t') {
      int32_t ch = lookahead(lexer);
      if (token_len < MAX_TODO_KW_LEN - 1) {
        token[token_len++] = (char)ch;
      }
      advance(lexer);
    }
    token[token_len] = '\0';

    if (token_len == 0) continue;
    if (token_len == 1 && token[0] == '|') continue;

    char keyword[MAX_TODO_KW_LEN];
    int kw_len = 0;
    bool saw_upper = false;
    for (int i = 0; i < token_len; i++) {
      if (token[i] == '(') break;
      if (!is_todo_keyword_char(token[i])) {
        kw_len = 0;
        saw_upper = false;
        break;
      }
      if (is_ascii_upper(token[i])) saw_upper = true;
      if (kw_len < MAX_TODO_KW_LEN - 1) {
        keyword[kw_len++] = token[i];
      }
    }
    keyword[kw_len] = '\0';

    if (kw_len > 0 && saw_upper) {
      scanner_add_todo_keyword(s, keyword);
    }
  }

  lexer->result_symbol = TOKEN_TODO_SETUP_SYNC;
  return true;
}

// _FIXED_WIDTH_COLON: gate token for fixed-width line starts.
//
// Emitted only when ':' is the first non-whitespace character on the line,
// enforcing the spec constraint:
//   _fixed_width_line <- _BOL _INDENT? ':' (' ' value:[^\n]* / &_NL) _NL
//
// Two cases are handled:
//
//   Column 0: skip any leading whitespace (indentation), then check for ':'
//   followed by ' ' or '\n'/EOF.  Consuming the indent + ':' here means the
//   grammar rule never needs an explicit _INDENT? prefix.
//
//   Column > 0 with prev_char == 0: we left column 0 via grammar/internal
//   tokens only, so no visible scanner token has consumed text on this line
//   yet. We treat this as a valid BOL context for indented fixed-width lines.
//
// In all other cases (column > 0 with prev_char != 0, meaning external scanner
// has already consumed visible content on this line) we return false.  The
// ':' will be consumed by scan_plain_text instead.
// Return values:
//   1  -> TOKEN_FIXED_WIDTH_COLON emitted
//   0  -> no match, no advance made
//  -1  -> no match, but advance(s) were made; caller must immediately
//         return false so tree-sitter rewinds before trying other tokens.
static int scan_fixed_width_colon(Scanner *s, TSLexer *lexer, const bool *valid_symbols) {
  bool advanced = false;

  if (get_column(lexer) == 0) {
    // Column-0 fixed-width lines are valid.
  } else {
    // Mid-line: only valid if no visible external text was consumed on this
    // line (pure BOL path via grammar/internal tokens).
    if (s->prev_char != 0) return 0;
  }

  if (lookahead(lexer) != ':') {
    if (advanced && valid_symbols[TOKEN_PLAIN_TEXT]) {
      int32_t last = ' ';
      while (!eof(lexer) && lookahead(lexer) != '\n' && !is_special_char(lookahead(lexer))) {
        last = lookahead(lexer);
        advance(lexer);
      }
      lexer->result_symbol = TOKEN_PLAIN_TEXT;
      mark_end(lexer);
      s->prev_char = last;
      return 1;
    }
    return advanced ? -1 : 0;
  }
  advance(lexer);  // consume ':'
  advanced = true;

  // ':' must be followed by a space, newline, or EOF to qualify
  int32_t next = lookahead(lexer);
  if (next != ' ' && next != '\n' && !eof(lexer)) return -1;

  mark_end(lexer);
  lexer->result_symbol = TOKEN_FIXED_WIDTH_COLON;
  return 1;
}

// ---------------------------------------------------------------------------
// Main scan function
// ---------------------------------------------------------------------------

bool tree_sitter_org_external_scanner_scan(
    void *payload,
    TSLexer *lexer,
    const bool *valid_symbols
) {
  Scanner *s = (Scanner *)payload;
  uint32_t col = get_column(lexer);

  // Error recovery sentinel — never match
  if (valid_symbols[TOKEN_ERROR_SENTINEL]) {
    return false;
  }

  // Special-keyword sync hook used to update TODO keyword set from #+TODO.
  if (valid_symbols[TOKEN_TODO_SETUP_SYNC]) {
    if (scan_todo_setup_sync(s, lexer)) return true;
  }

  // Affiliated-keyword sync hook used to reset table state between elements.
  if (valid_symbols[TOKEN_AFFILIATED_SYNC]) {
    if (scan_affiliated_sync(s, lexer)) return true;
  }

  if (valid_symbols[TOKEN_DRAWER_ENTER_SYNC]) {
    if (scan_drawer_enter_sync(s, lexer)) return true;
  }

  if (valid_symbols[TOKEN_DRAWER_EXIT_SYNC]) {
    if (scan_drawer_exit_sync(s, lexer)) return true;
  }

  // _NL is a grammar regex and never updates prev_char.  Reset it to 0
  // (BOL) whenever we are positioned at the start of a new line so that
  // markup scanners correctly treat the beginning-of-line as a valid PRE
  // context, even after a line that ended with a non-PRE character.
  if (col == 0) {
    if (s->suppress_block_begin_on_end_line &&
        lookahead(lexer) != ' ' && lookahead(lexer) != '\t') {
      s->suppress_block_begin_on_end_line = false;
    }

    s->prev_char = 0;
    s->plain_lbracket_depth = 0;
    s->in_heading_line = false;
    s->bol_shifted_by_grammar = false;
    reset_markup_open_state(s);

    // Keep table state in sync across element boundaries even when
    // TOKEN_TABLE_START is not probed on an intervening line (for example,
    // blank lines, heading stars, comments/keywords before the next table).
    // Without this, `in_table` can leak past the end of a table and block
    // later tables in the same document.
    int32_t ch = lookahead(lexer);
    if (s->in_table && ch != '|' && ch != ' ' && ch != '\t') {
      s->in_table = false;
    }
  } else if (col <= s->last_column) {
    // We moved to a new line without a scanner callback at column 0.
    // This commonly happens when grammar regexes consume `\n` and list
    // bullets (`- `, `+ `, `1. `, etc.) before the scanner is consulted.
    // In that case, treat context as PRE-whitespace so inline markup can
    // open at the beginning of the list item text.
    s->prev_char = s->section_block_depth > 0 ? 0 : ' ';
    s->plain_lbracket_depth = 0;
    s->in_heading_line = false;
    s->bol_shifted_by_grammar = true;
  } else if (col > 0 && s->last_column == 0 && s->prev_char == 0) {
    // We left column 0 via grammar/internal tokens only (for example list
    // bullets/spaces or heading stars/space). No external scanner token has
    // consumed visible text on this line yet, so markup PRE context should be
    // whitespace at this position.
    if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      s->prev_char = ' ';
    } else if (s->section_block_depth == 0) {
      s->prev_char = ' ';
    }
    s->bol_shifted_by_grammar = true;
  } else {
    s->bol_shifted_by_grammar = false;
  }

  s->last_column = (uint16_t)(col > 0xFFFF ? 0xFFFF : col);

  // --- HEADING_END at EOF ---
  if (valid_symbols[TOKEN_HEADING_END]) {
    if (scan_heading_end_eof(s, lexer)) return true;
  }

  // --- STARS / HEADING_END at column 0 (combined) ---
  // These must be handled together because both need to peek at
  // the stars pattern at column 0, and advancing the lexer to
  // count stars is irreversible within a single scan call.
  if (valid_symbols[TOKEN_STARS] || valid_symbols[TOKEN_HEADING_END]) {
    if (scan_stars_or_heading_end(s, lexer, valid_symbols)) return true;
  }

  // --- BLOCK_PARAGRAPH_CONTINUE ---
  // Outside drawers, probe paragraph continuation before block delimiters.
  // Inside drawers, probe block delimiters first so dedent/`:end:` handling
  // can close nested list-item blocks before parsing the drawer terminator.
  if (s->drawer_depth == 0 &&
      valid_symbols[TOKEN_INDENT_PARAGRAPH_CONTINUE] &&
      !valid_symbols[TOKEN_INDENT_END]) {
    int result = scan_block_paragraph_continue(s, lexer);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  // --- Section indentation blocks ---
  // Block delimiters own indentation structure for all section elements.
  if (valid_symbols[TOKEN_INDENT_END]) {
    int result = scan_block_end(s, lexer, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  if (valid_symbols[TOKEN_INDENT_BEGIN]) {
    int result = scan_block_begin(s, lexer, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  if (!valid_symbols[TOKEN_INDENT_END] &&
      valid_symbols[TOKEN_INDENT_CONTENT_CONTINUE]) {
    int result = scan_block_content_continue(s, lexer, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  if (!valid_symbols[TOKEN_INDENT_END] &&
      valid_symbols[TOKEN_INDENT_LIST_ITEM_CONTINUE]) {
    int result = scan_block_list_item_continue(s, lexer);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  if (s->drawer_depth > 0 && valid_symbols[TOKEN_INDENT_PARAGRAPH_CONTINUE]) {
    int result = scan_block_paragraph_continue(s, lexer);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  // --- TABLE management (zero-width) ---
  if (valid_symbols[TOKEN_TABLE_START]) {
    int result = scan_table_start(s, lexer);
    if (result == 1) return true;
  }

  if (valid_symbols[TOKEN_TABLE_BREAK_SYNC]) {
    int result = scan_table_break_sync(s, lexer);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  // --- FNDEF_END ---
  if (valid_symbols[TOKEN_FNDEF_END]) {
    if (scan_fndef_end(s, lexer)) return true;
  }

  // --- TODO_KW ---
  if (valid_symbols[TOKEN_TODO_KW]) {
    if (scan_todo_kw(s, lexer, valid_symbols)) return true;
  }

  // --- COMMENT_TOKEN ---
  // Runs after scan_todo_kw so that a user-defined TODO keyword named COMMENT
  // is matched by scan_todo_kw first (TOKEN_TODO_KW wins).  When COMMENT is
  // not a TODO keyword, scan_todo_kw bails out and we handle it here.
  if (valid_symbols[TOKEN_COMMENT_TOKEN]) {
    if (scan_comment_token(s, lexer)) return true;
  }

  // --- GBLOCK_NAME ---
  if (valid_symbols[TOKEN_GBLOCK_NAME]) {
    if (scan_gblock_name(s, lexer)) return true;
  }

  // --- BLOCK_END_MATCH ---
  if (valid_symbols[TOKEN_BLOCK_END_MATCH]) {
    if (scan_block_end_match(s, lexer)) return true;
  }

  // --- ITEM_TAG_END ---
  if (valid_symbols[TOKEN_ITEM_TAG_END]) {
    if (scan_item_tag_end(s, lexer)) return true;
  }

  // --- Markup close tokens ---
  // Close checks must run before open checks so boundary-heavy nested forms
  // like */bold-italic/* or /..._..._/ emit the closing marker instead of
  // speculatively probing an opener and forcing recovery.
  if (valid_symbols[TOKEN_MARKUP_CLOSE_BOLD]) {
    int result = scan_markup_close(s, lexer, '*', TOKEN_MARKUP_CLOSE_BOLD);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_ITALIC]) {
    int result = scan_markup_close(s, lexer, '/', TOKEN_MARKUP_CLOSE_ITALIC);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_UNDERLINE]) {
    int result = scan_markup_close(s, lexer, '_', TOKEN_MARKUP_CLOSE_UNDERLINE);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_STRIKE]) {
    int result = scan_markup_close(s, lexer, '+', TOKEN_MARKUP_CLOSE_STRIKE);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_VERBATIM]) {
    int result = scan_markup_close(s, lexer, '=', TOKEN_MARKUP_CLOSE_VERBATIM);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_CODE]) {
    int result = scan_markup_close(s, lexer, '~', TOKEN_MARKUP_CLOSE_CODE);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  // --- Markup open tokens ---
  if (valid_symbols[TOKEN_MARKUP_OPEN_BOLD]) {
    int result = scan_markup_open(s, lexer, '*', TOKEN_MARKUP_OPEN_BOLD, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_ITALIC]) {
    int result = scan_markup_open(s, lexer, '/', TOKEN_MARKUP_OPEN_ITALIC, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_UNDERLINE]) {
    int result = scan_markup_open(s, lexer, '_', TOKEN_MARKUP_OPEN_UNDERLINE, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_STRIKE]) {
    int result = scan_markup_open(s, lexer, '+', TOKEN_MARKUP_OPEN_STRIKE, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_VERBATIM]) {
    int result = scan_markup_open(s, lexer, '=', TOKEN_MARKUP_OPEN_VERBATIM, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_CODE]) {
    int result = scan_markup_open(s, lexer, '~', TOKEN_MARKUP_OPEN_CODE, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  // --- PLAN_KW (planning keywords) ---
  if (valid_symbols[TOKEN_PLAN_KW]) {
    if (scan_plan_kw(s, lexer, valid_symbols)) return true;
  }

  // --- DYNBLOCK_SYNC ---
  if (valid_symbols[TOKEN_DYNBLOCK_SYNC]) {
    if (scan_dynblock_sync(s, lexer)) return true;
  }

  // --- FIXED_WIDTH_COLON (element-level BOL gate) ---
  // Must run before PLAIN_TEXT so that "   : value" at column 0 emits
  // TOKEN_FIXED_WIDTH_COLON rather than TOKEN_PLAIN_TEXT for the indent.
  if (valid_symbols[TOKEN_FIXED_WIDTH_COLON]) {
    int result = scan_fixed_width_colon(s, lexer, valid_symbols);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  // --- PARAGRAPH_CONTINUE ---
  if (valid_symbols[TOKEN_PARAGRAPH_CONTINUE]) {
    int result = scan_paragraph_continue(lexer);
    if (result == 1) return true;
    if (result == -1) return false;
  }

  // --- INLINE_BABEL_START / INLINE_SRC_START / INLINE_BABEL_OUTSIDE_HEADER_START / PLAIN_TEXT ---
  // scan_inline_babel_start and scan_inline_src_start are checked first.  If
  // either one returns false after having called advance() (i.e. consumed one
  // or more characters), the lexer is left past those characters.  We detect
  // this by comparing get_column() before and after each attempt and pass the
  // result to scan_plain_text so its recovery guard fires only when chars were
  // actually consumed — not merely because the scan was called mid-line.
  {
    uint32_t col_before = get_column(lexer);
    bool prev_scanner_advanced = false;

    if (valid_symbols[TOKEN_INLINE_BABEL_START]) {
      if (scan_inline_babel_start(s, lexer)) return true;
      prev_scanner_advanced = (get_column(lexer) > col_before);
    }

    if (valid_symbols[TOKEN_INLINE_SRC_START]) {
      if (scan_inline_src_start(s, lexer)) return true;
      if (!prev_scanner_advanced)
        prev_scanner_advanced = (get_column(lexer) > col_before);
    }

    if (valid_symbols[TOKEN_INLINE_BABEL_OUTSIDE_HEADER_START]) {
      if (scan_inline_babel_outside_header_start(lexer)) return true;
    }

    if (valid_symbols[TOKEN_PLAIN_TEXT]) {
      if (scan_plain_text(s, lexer, valid_symbols, prev_scanner_advanced)) return true;
    }
  }

  return false;
}
