/**
 * tree-sitter-org external scanner.
 *
 * Handles context-sensitive features that tree-sitter's grammar DSL
 * cannot express (syntax.md §12):
 *
 *   - Beginning-of-line detection (BOL via get_column)
 *   - Heading level tracking and containment
 *   - List indentation grouping
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
  TOKEN_LIST_START,
  TOKEN_LIST_END,
  TOKEN_ITEM_END,
  TOKEN_TODO_KW,
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
  TOKEN_FNDEF_END,
  TOKEN_PLAIN_TEXT,
  TOKEN_ITEM_TAG_END,
  TOKEN_LISTITEM_INDENT,
  TOKEN_PLAN_KW,
  TOKEN_ERROR_SENTINEL,
  TOKEN_TABLE_START,   // zero-width gate emitted once at the start of each org_table
  TOKEN_FIXED_WIDTH_COLON, // consumes optional indent + ':' only at BOL context
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
#define MAX_HEADING_DEPTH   64
#define MAX_LIST_DEPTH      64
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
         ch == 0;
}

// Character that could start an object or element (for plain_text scanning)
// This must be conservative: plain_text scanning stops at any character
// that might start an object, markup, element, or special syntax.
static bool is_special_char(int32_t ch) {
  return ch == '*' || ch == '/' || ch == '_' || ch == '+' ||
         ch == '=' || ch == '~' || ch == '[' || ch == '<' ||
         ch == '{' || ch == '\\' || ch == '@' ||
         ch == '#' || ch == ':' || ch == '|' || ch == '>' ||
         ch == '-' || ch == ']';
}

// ---------------------------------------------------------------------------
// Scanner state
// ---------------------------------------------------------------------------
typedef struct {
  // Heading level stack
  uint8_t heading_levels[MAX_HEADING_DEPTH];
  uint8_t heading_depth;

  // List indentation stack
  uint16_t list_indents[MAX_LIST_DEPTH];
  uint8_t list_depth;

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

  // Table tracking: true while the parser is inside an org_table.
  // Used by scan_table_start to prevent starting a new org_table mid-table,
  // which would cause each row to parse as a separate org_table node.
  bool in_table;
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

  // list_depth + indents (2 bytes each)
  if (pos + 1 + s->list_depth * 2 > SERIALIZE_BUF_SIZE) return 0;
  buffer[pos++] = (char)s->list_depth;
  for (uint8_t i = 0; i < s->list_depth; i++) {
    buffer[pos++] = (char)(s->list_indents[i] >> 8);
    buffer[pos++] = (char)(s->list_indents[i] & 0xFF);
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

  // prev_char, consecutive_blank_lines, in_table
  if (pos + 6 > SERIALIZE_BUF_SIZE) return 0;
  buffer[pos++] = (char)((s->prev_char >> 24) & 0xFF);
  buffer[pos++] = (char)((s->prev_char >> 16) & 0xFF);
  buffer[pos++] = (char)((s->prev_char >> 8) & 0xFF);
  buffer[pos++] = (char)(s->prev_char & 0xFF);
  buffer[pos++] = (char)s->consecutive_blank_lines;
  buffer[pos++] = (char)(s->in_table ? 1 : 0);

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
  s->list_depth = 0;
  s->block_depth = 0;
  s->prev_char = 0;
  s->consecutive_blank_lines = 0;

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

  // list_depth + indents
  if (pos >= length) return;
  s->list_depth = (uint8_t)buffer[pos++];
  for (uint8_t i = 0; i < s->list_depth && pos + 1 < length; i++) {
    s->list_indents[i] = (uint16_t)((uint8_t)buffer[pos] << 8 | (uint8_t)buffer[pos + 1]);
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

  // prev_char, consecutive_blank_lines, in_table
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
// If the word isn't a TODO keyword but was consumed, emit as PLAIN_TEXT
// to avoid corrupting the lexer state.
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

  while (lookahead(lexer) >= 'A' && lookahead(lexer) <= 'Z' && len < MAX_TODO_KW_LEN - 1) {
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

  // Not a TODO keyword but we consumed uppercase letters.
  // Emit as plain text to avoid corrupting lexer state.
  // Continue consuming the rest of the "word" as plain text.
  bool continuation_ran = false;
  while (!eof(lexer) && lookahead(lexer) != '\n' && !is_special_char(lookahead(lexer))) {
    s->prev_char = lookahead(lexer);
    advance(lexer);
    continuation_ran = true;
  }
  if (valid_symbols[TOKEN_PLAIN_TEXT]) {
    // If the continuation loop did not advance (e.g. the word was immediately
    // followed by a special char like '*'), prev_char should be the last
    // uppercase letter we consumed.  If the loop did run, prev_char was already
    // updated to the correct last character inside the loop — do not overwrite.
    if (!continuation_ran) {
      s->prev_char = word[len - 1];
    }
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    mark_end(lexer);
    return true;
  }

  return false;
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

// Markup open: PRE check + advance marker + verify no whitespace after
static bool scan_markup_open(Scanner *s, TSLexer *lexer, int32_t marker, enum TokenType token) {
  if (!is_markup_pre(s->prev_char)) return false;
  if (lookahead(lexer) != marker) return false;

  advance(lexer);

  int32_t next = lookahead(lexer);
  if (next == ' ' || next == '\t' || next == '\n' || eof(lexer)) return false;

  lexer->result_symbol = token;
  mark_end(lexer);
  s->prev_char = marker;
  return true;
}

// Markup close: no whitespace before + advance marker + POST check
static bool scan_markup_close(Scanner *s, TSLexer *lexer, int32_t marker, enum TokenType token) {
  if (s->prev_char == ' ' || s->prev_char == '\t' || s->prev_char == '\n') return false;
  if (lookahead(lexer) != marker) return false;

  advance(lexer);

  int32_t next = lookahead(lexer);
  if (eof(lexer) || is_markup_post(next)) {
    lexer->result_symbol = token;
    mark_end(lexer);
    s->prev_char = marker;
    return true;
  }

  return false;
}

// _LIST_START: zero-width token emitted at the start of a plain_list.
//
// Lists are parsed FLAT: all items (including indented/nested ones) are
// siblings inside a single plain_list node.  The _LISTITEM_INDENT field on
// each item records its leading whitespace so that post-processing can
// reconstruct the proper nested structure.
//
// Consequently, _LIST_START only fires when we are NOT already inside a list
// (list_depth == 0).  Once a list is open, every subsequent bullet becomes a
// sibling item without a new _LIST_START.
//
// Returns: 1=matched LIST_START, 0=no match
static int scan_list_start(Scanner *s, TSLexer *lexer, const bool *valid_symbols) {
  if (s->list_depth >= MAX_LIST_DEPTH) return 0;

  // Flat lists only: never start a nested list.
  if (s->list_depth > 0) return 0;

  mark_end(lexer);  // zero-width token position

  uint32_t col = get_column(lexer);
  int32_t ch = lookahead(lexer);

  if (ch == '+' || ch == '-') {
    advance(lexer);
    if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      s->list_indents[s->list_depth] = (uint16_t)col;
      s->list_depth++;
      lexer->result_symbol = TOKEN_LIST_START;
      return 1;
    }

    // Recovery for '+' at BOL/non-list contexts (e.g. "+strike+").
    // scan_list_start probes list bullets before markup scanners; if we
    // consumed '+' and it is not a bullet, emit strike-open when valid.
    if (ch == '+' && valid_symbols[TOKEN_MARKUP_OPEN_STRIKE] &&
        is_markup_pre(s->prev_char) && lookahead(lexer) != ' ' &&
        lookahead(lexer) != '\t' && lookahead(lexer) != '\n' && !eof(lexer)) {
      lexer->result_symbol = TOKEN_MARKUP_OPEN_STRIKE;
      mark_end(lexer);
      s->prev_char = '+';
      return 1;
    }

    return 0;
  }

  if (ch == '*' && col > 0) {
    advance(lexer);
    if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      s->list_indents[s->list_depth] = (uint16_t)col;
      s->list_depth++;
      lexer->result_symbol = TOKEN_LIST_START;
      return 1;
    }
    return 0;
  }

  if ((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'z')) {
    if (ch >= '0' && ch <= '9') {
      while (lookahead(lexer) >= '0' && lookahead(lexer) <= '9') {
        advance(lexer);
      }
    } else {
      advance(lexer);
    }
    if (lookahead(lexer) == '.' || lookahead(lexer) == ')') {
      advance(lexer);
      if (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
        s->list_indents[s->list_depth] = (uint16_t)col;
        s->list_depth++;
        lexer->result_symbol = TOKEN_LIST_START;
        return 1;
      }
    }
    return 0;
  }

  return 0;
}

// _LIST_END: zero-width token emitted when the plain_list closes.
//
// Because lists are flat (see scan_list_start above), we end the list
// whenever the next real character cannot start a list item or blank line.
// This check is intentionally NON-ADVANCING: we only look at the current
// lookahead character (and its column) without calling advance().  This
// avoids corrupting the lexer position for subsequent scanners in the same
// outer scan() call.
//
// Characters that mean the list CONTINUES (return false):
//   '\n'           — blank line; the _blank_line rule in plain_list handles it
//   ' ' / '\t'     — whitespace; scan_listitem_indent runs before us and
//                    handles indented bullets.  If it returned -1 (indented
//                    non-bullet), the outer function falls through here and
//                    we see the non-bullet character instead of the space.
//   '-' / '+'      — unordered bullet
//   '0'..'9'       — ordered bullet (digit counter)
//   'a'..'z'       — ordered bullet (letter counter)
//   '*' at col > 0 — unordered star bullet (col 0 would be a heading)
//
// Everything else (heading '*' at col 0, '#', ':', etc.) ends the list.
static bool scan_list_end(Scanner *s, TSLexer *lexer) {
  if (s->list_depth == 0) return false;

  mark_end(lexer);  // zero-width; position set here (may be after whitespace
                    // if scan_listitem_indent advanced in the -1 case)

  if (eof(lexer)) {
    s->list_depth--;
    lexer->result_symbol = TOKEN_LIST_END;
    return true;
  }

  int32_t ch = lookahead(lexer);
  uint32_t col = get_column(lexer);

  if (ch == '\n') return false;                 // blank line
  if (ch == ' ' || ch == '\t') return false;    // whitespace (LISTITEM_INDENT)
  if (ch == '-' || ch == '+') return false;     // unordered bullet
  if (ch >= '0' && ch <= '9') return false;     // ordered bullet (digit)
  if (ch >= 'a' && ch <= 'z') return false;     // ordered bullet (letter)
  if (ch == '*' && col > 0) return false;       // star bullet (non-heading)

  // Heading '*' at col 0, keywords ('#'), drawers (':'), etc. — end the list.
  s->list_depth--;
  lexer->result_symbol = TOKEN_LIST_END;
  return true;
}

// _ITEM_END: only emit at EOF or double blank line when in a list
static bool scan_item_end(Scanner *s, TSLexer *lexer) {
  if (s->list_depth == 0) return false;
  if (eof(lexer) || s->consecutive_blank_lines >= 2) {
    lexer->result_symbol = TOKEN_ITEM_END;
    mark_end(lexer);
    s->consecutive_blank_lines = 0;
    return true;
  }
  return false;
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
static bool scan_item_tag_end(TSLexer *lexer) {
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
  return false;
}

// _LISTITEM_INDENT: leading whitespace before an indented list item bullet.
//
// Used by optional(field('indent', _LISTITEM_INDENT)) in the item rule to
// record the item's indentation column.  By preserving this in the tree,
// post-processing can reconstruct proper nested list structure.
//
// Only fires when whitespace is followed by a valid bullet character, so it
// never interferes with non-bullet indented content (paragraphs, blocks, …).
//
// Return values (three-state to let the outer scan() make the right decision):
//   1  — whitespace + bullet: _LISTITEM_INDENT token emitted (advance committed)
//   0  — no leading whitespace: no advance, fall through to other scanners
//  -1  — whitespace + non-bullet non-newline: advance made, no token; the outer
//         function should fall through to scan_list_end so the list can close
//  -2  — whitespace + '\n' or EOF (whitespace-only line): advance made, no token;
//         the outer function should return false so tree-sitter resets the lexer
//         and the internal _blank_line rule can match "[ \t]*\n"
static int scan_listitem_indent(TSLexer *lexer) {
  if (lookahead(lexer) != ' ' && lookahead(lexer) != '\t') return 0;

  mark_end(lexer);

  while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
    advance(lexer);
  }

  int32_t ch = lookahead(lexer);

  // Bullet characters: unordered (-, +, *) or ordered (digit, lowercase letter)
  if (ch == '+' || ch == '-' || ch == '*' ||
      (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'z')) {
    lexer->result_symbol = TOKEN_LISTITEM_INDENT;
    mark_end(lexer);
    return 1;
  }

  // Whitespace-only line or EOF after whitespace — let _blank_line handle it.
  if (ch == '\n' || eof(lexer)) return -2;

  // Non-bullet, non-blank content (e.g. "  some paragraph") — the list should
  // end here; signal the outer function to fall through to scan_list_end.
  return -1;
}

// Characters that could start internal grammar tokens (elements/objects)
// and should NOT be consumed as plain text fallback.
static bool is_internal_token_start(int32_t ch) {
  return ch == '#' || ch == ':' || ch == '|' || ch == '[' ||
         ch == '<' || ch == '@' || ch == '{' || ch == '\\' ||
         ch == '>' || ch == ']' || ch == '-';
}

static bool is_heading_tag_char(int32_t ch) {
  return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
         (ch >= '0' && ch <= '9') || ch == '_' || ch == '@' ||
         ch == '#' || ch == '%';
}

// _PLAIN_TEXT: scan forward to next object/element boundary
// Consumes "safe" characters that cannot start an object or element.
// If positioned at a markup character (*/_ +=~) that the markup scanner
// already rejected, consumes it as plain text to keep prev_char accurate.
static bool scan_plain_text(Scanner *s, TSLexer *lexer) {
  if (eof(lexer) || lookahead(lexer) == '\n') return false;

  bool found_any = false;

  while (!eof(lexer) && lookahead(lexer) != '\n') {
    int32_t ch = lookahead(lexer);

    // Stop at any character that could start an object or element
    if (is_special_char(ch)) break;

    s->prev_char = ch;
    advance(lexer);
    mark_end(lexer);
    found_any = true;
  }

  // If we consumed some non-special chars, return them as plain text
  if (found_any) {
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    return true;
  }

  // We're at a special character. If it could start an internal grammar
  // token, do NOT consume it — the grammar needs a chance to try.
  // Only consume markup-related chars (*/_+=~) as single-char fallback,
  // since the markup open/close scanners already tried and failed.
  int32_t ch = lookahead(lexer);
  if (ch == ':') {
    // Mid-line colons are often plain text ("test ::", "value: text").
    // But if ':' is followed by a heading-tag character, prefer letting
    // the grammar parse tags (e.g. "* Title :tag:"). We probe one char
    // ahead and, in the tag-like case, return false so this scan call is
    // discarded and parsing retries from the original ':' position.
    advance(lexer);
    int32_t next = lookahead(lexer);
    if (is_heading_tag_char(next)) {
      return false;
    }

    s->prev_char = ':';
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    return true;
  }

  if (!is_internal_token_start(ch)) {
    s->prev_char = ch;
    advance(lexer);
    mark_end(lexer);
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
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
// If the keyword doesn't match after partially advancing, emit consumed
// text as PLAIN_TEXT to avoid corrupting lexer state.
static bool scan_plan_kw(Scanner *s, TSLexer *lexer, const bool *valid_symbols) {
  int32_t ch = lookahead(lexer);
  const char *kw = NULL;

  if (ch == 'D') kw = "DEADLINE";
  else if (ch == 'S') kw = "SCHEDULED";
  else if (ch == 'C') kw = "CLOSED";
  else return false;

  mark_end(lexer);

  if (match_string(lexer, kw)) {
    lexer->result_symbol = TOKEN_PLAN_KW;
    mark_end(lexer);
    return true;
  }

  // Partial match failed. We've advanced the lexer. Recover by
  // consuming the rest as plain text.
  while (!eof(lexer) && lookahead(lexer) != '\n' && !is_special_char(lookahead(lexer))) {
    s->prev_char = lookahead(lexer);
    advance(lexer);
  }
  if (valid_symbols[TOKEN_PLAIN_TEXT]) {
    lexer->result_symbol = TOKEN_PLAIN_TEXT;
    mark_end(lexer);
    return true;
  }
  return false;
}

// _PARAGRAPH_CONTINUE
static bool scan_paragraph_continue(TSLexer *lexer) {
  if (get_column(lexer) != 0) return false;

  int32_t ch = lookahead(lexer);

  // Element-starting patterns at BOL
  if (ch == '*' || ch == '#' || ch == ':' || ch == '|' ||
      ch == '+' || ch == '-' || ch == '[' || ch == '%' ||
      ch == 'C' || ch == 'D' || ch == 'S' ||
      ch == '\n' || (ch >= '0' && ch <= '9') ||
      (ch >= 'a' && ch <= 'z') || eof(lexer)) {
    return false;
  }

  lexer->result_symbol = TOKEN_PARAGRAPH_CONTINUE;
  mark_end(lexer);
  return true;
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
//   Column > 0 with prev_char == 0: the list scanner (scan_listitem_indent +
//   scan_list_end) can advance past indentation and then emit a zero-width
//   LIST_END, leaving the lexer positioned mid-line at ':'.  Because only
//   zero-width / internal tokens ran, prev_char is still 0 even at column > 0.
//   We treat this as a valid BOL context for indented fixed-width lines inside
//   list items.
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
    // Skip optional leading whitespace (indentation)
    while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') {
      advance(lexer);
      advanced = true;
    }
  } else {
    // Mid-line: only valid if prev_char == 0 (no external text on this line)
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

  // Error recovery sentinel — never match
  if (valid_symbols[TOKEN_ERROR_SENTINEL]) {
    return false;
  }

  // _NL is a grammar regex and never updates prev_char.  Reset it to 0
  // (BOL) whenever we are positioned at the start of a new line so that
  // markup scanners correctly treat the beginning-of-line as a valid PRE
  // context, even after a line that ended with a non-PRE character.
  if (get_column(lexer) == 0) {
    s->prev_char = 0;
  }

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

  // --- LISTITEM_INDENT + LIST_END (tightly coupled) ---
  //
  // scan_listitem_indent must run before scan_list_end for two reasons:
  //   1. For indented bullets ("  - item"), LISTITEM_INDENT must fire first
  //      to emit the indent token; LIST_END must not prematurely close the list.
  //   2. scan_list_end is now non-advancing (no peek_bullet_column), so it
  //      cannot distinguish "  - bullet" from "  non-bullet".  scan_listitem_indent
  //      advances past the whitespace and signals the result via its return code,
  //      letting scan_list_end then see the actual first non-whitespace character.
  //
  // Return-code protocol for scan_listitem_indent:
  //    1  → LISTITEM_INDENT emitted; done.
  //    0  → no leading whitespace; fall through to LIST_START / LIST_END.
  //   -1  → whitespace consumed, non-bullet follows; fall through to LIST_END
  //          so it can fire at the non-bullet character (consuming the whitespace
  //          as part of the hidden LIST_END token is acceptable).
  //   -2  → whitespace consumed, blank line follows; return false so tree-sitter
  //          resets the lexer and the internal _blank_line rule can match.
  if (valid_symbols[TOKEN_LISTITEM_INDENT]) {
    int result = scan_listitem_indent(lexer);
    if (result == 1) return true;
    if (result == -2) return false;   // whitespace-only line — reset for _blank_line
    if (result == -1) {
      // Indented non-bullet content. Lexer is now past the whitespace.
      // Fall directly to scan_list_end; skip LIST_START (can't start inside list).
      if (valid_symbols[TOKEN_LIST_END]) {
        if (scan_list_end(s, lexer)) return true;
      }
      return false;
    }
    // result == 0: no leading whitespace; fall through normally.
  }

  // --- LIST management (zero-width) ---
  if (valid_symbols[TOKEN_LIST_START]) {
    int result = scan_list_start(s, lexer, valid_symbols);
    if (result == 1) return true;
    // result == 0: no match; no advance was made.
  }

  if (valid_symbols[TOKEN_LIST_END]) {
    if (scan_list_end(s, lexer)) return true;
  }

  if (valid_symbols[TOKEN_ITEM_END]) {
    if (scan_item_end(s, lexer)) return true;
  }

  // --- TABLE management (zero-width) ---
  if (valid_symbols[TOKEN_TABLE_START]) {
    int result = scan_table_start(s, lexer);
    if (result == 1) return true;
  }

  // --- FNDEF_END ---
  if (valid_symbols[TOKEN_FNDEF_END]) {
    if (scan_fndef_end(s, lexer)) return true;
  }

  // --- TODO_KW ---
  if (valid_symbols[TOKEN_TODO_KW]) {
    if (scan_todo_kw(s, lexer, valid_symbols)) return true;
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
    if (scan_item_tag_end(lexer)) return true;
  }

  // --- Markup open tokens ---
  if (valid_symbols[TOKEN_MARKUP_OPEN_BOLD]) {
    if (scan_markup_open(s, lexer, '*', TOKEN_MARKUP_OPEN_BOLD)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_ITALIC]) {
    if (scan_markup_open(s, lexer, '/', TOKEN_MARKUP_OPEN_ITALIC)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_UNDERLINE]) {
    if (scan_markup_open(s, lexer, '_', TOKEN_MARKUP_OPEN_UNDERLINE)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_STRIKE]) {
    if (scan_markup_open(s, lexer, '+', TOKEN_MARKUP_OPEN_STRIKE)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_VERBATIM]) {
    if (scan_markup_open(s, lexer, '=', TOKEN_MARKUP_OPEN_VERBATIM)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_OPEN_CODE]) {
    if (scan_markup_open(s, lexer, '~', TOKEN_MARKUP_OPEN_CODE)) return true;
  }

  // --- Markup close tokens ---
  if (valid_symbols[TOKEN_MARKUP_CLOSE_BOLD]) {
    if (scan_markup_close(s, lexer, '*', TOKEN_MARKUP_CLOSE_BOLD)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_ITALIC]) {
    if (scan_markup_close(s, lexer, '/', TOKEN_MARKUP_CLOSE_ITALIC)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_UNDERLINE]) {
    if (scan_markup_close(s, lexer, '_', TOKEN_MARKUP_CLOSE_UNDERLINE)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_STRIKE]) {
    if (scan_markup_close(s, lexer, '+', TOKEN_MARKUP_CLOSE_STRIKE)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_VERBATIM]) {
    if (scan_markup_close(s, lexer, '=', TOKEN_MARKUP_CLOSE_VERBATIM)) return true;
  }
  if (valid_symbols[TOKEN_MARKUP_CLOSE_CODE]) {
    if (scan_markup_close(s, lexer, '~', TOKEN_MARKUP_CLOSE_CODE)) return true;
  }

  // --- PLAN_KW (planning keywords) ---
  if (valid_symbols[TOKEN_PLAN_KW]) {
    if (scan_plan_kw(s, lexer, valid_symbols)) return true;
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
    if (scan_paragraph_continue(lexer)) return true;
  }

  // --- PLAIN_TEXT (fallback) ---
  if (valid_symbols[TOKEN_PLAIN_TEXT]) {
    if (scan_plain_text(s, lexer)) return true;
  }

  return false;
}
