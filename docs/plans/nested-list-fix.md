The Fix (scanner.c only, no grammar.js changes)

### 1. `scan_list_start`: Skip whitespace + indent guard

Change from detecting the bullet at the immediate position to **skipping whitespace first** (so it finds indented bullets for nested lists), and add a guard so it **returns 0 when `col <= current_list_indent`** (same-level bullets stay as siblings, not new nested lists).

The token remains zero-width (`mark_end` is called before advancing), so after `_LIST_START` fires at the whitespace position, the lexer resets to that same position. The whitespace is then consumed by `_LISTITEM_INDENT` as part of the inner list's first item.

```c
// BEFORE advancing: mark zero-width position
mark_end(lexer);

// Skip whitespace to reach bullet character
while (lookahead(lexer) == ' ' || lookahead(lexer) == '\t') advance(lexer);

uint32_t col = get_column(lexer);

// Inside a list: only start a NESTED list (col strictly deeper than current level)
if (s->list_depth > 0 && col <= s->list_indents[s->list_depth - 1]) return 0;

// … rest of bullet matching unchanged …
```

Change all `-1` returns to `0` (letting tree-sitter rewind cleanly). Remove the `-1` recovery block in the main scan function.

### 2. `scan_list_end`: Don't fire when more items remain at current level

Add a **lookahead peek** that skips whitespace and checks whether the next content is a valid complete bullet at column ≥ current list's indent. If yes, return `false` — there are more items or a nested list starting in the item body.

Add a helper `peek_bullet_column` (does the thorough unordered+ordered bullet check including the required space after the marker).

```c
static bool scan_list_end(Scanner *s, TSLexer *lexer) {
  if (s->list_depth == 0) return false;

  mark_end(lexer);  // zero-width position

  int bullet_col = peek_bullet_column(lexer);  // peeks without consuming
  if (bullet_col >= 0 &&
      (uint16_t)bullet_col >= s->list_indents[s->list_depth - 1]) {
    return false;  // sibling item or deeper nested list coming — don't end
  }

  s->list_depth--;
  lexer->result_symbol = TOKEN_LIST_END;
  return true;
}
```

---

## Token Flow After Fix

For `- Test\n  - Nested\n  - Nested\n- Not nested`:

| Position | Token emitted | Reason |
|---|---|---|
| `- Test` col 0 | `_LIST_START` | depth=0, no indent check, fires |
| `- Test` | bullet + `first_line` + `_NL` | item A first line |
| `  - Nested` col 0 | `_LIST_START` (zero-width at col 0) | depth=1, col 2 > indent 0 ✓ |
| `  ` | `_LISTITEM_INDENT` | col 2 == inner list indent 2 ✓ |
| `- Nested` | bullet + `first_line` + `_NL` | inner item 1 |
| `  - Nested` col 0 | `peek_bullet_column` → col 2 ≥ 2 → don't end | inner list continues |
| `  ` | `_LISTITEM_INDENT` | inner item 2 |
| `- Nested` | bullet + `first_line` + `_NL` | inner item 2 |
| `- Not nested` col 0 | `peek_bullet_column` → col 0 < 2 → `_LIST_END` | inner list ends |
| body of "Test" ends | — | no more section elements |
| `- Not nested` col 0 | `peek_bullet_column` → col 0 ≥ 0 → don't end | outer list continues |
| `- Not nested` | bullet + `first_line` + `_NL` | outer item B |
| EOF | `peek_bullet_column` → -1 → `_LIST_END` | outer list ends |

---

## Test Corpus Changes

All **4 existing list tests** need their expected output updated — they currently reflect the broken deeply-nested behavior and will now produce correct sibling structure.

**New test** for the user's exact case:
```
- Test
  - Nested
  - Nested
- Not nested
```
→ `(plain_list (item (plain_text) (plain_list (item (plain_text)) (item (plain_text)))) (item (plain_text)))`

---

## Summary

- **Files changed**: `tree-sitter-org/src/scanner.c`, `tree-sitter-org/test/corpus/lists.txt`
- **Files NOT changed**: `grammar.js`, `parser.c`, serialization code
- **Rebuilding needed**: recompile only (no `tree-sitter generate` required since `grammar.js` is unchanged)

Two questions before I implement:

1. **Blank-line-separated lists** (`- A\n\n- B`): currently broken (outer list ends at blank line). My fix doesn't change this behavior — `peek_bullet_column` returns -1 at `\n`, so the list ends at the blank line. Should I also fix this, or is it out of scope?

2. **The `_LISTITEM_INDENT` node**: In the current tree, items have an `indent` field containing `_LISTITEM_INDENT`. After the fix, inner items will have this indent. Is that acceptable, or would you prefer the indent whitespace to be invisible in the tree (not surfaced as a node)?
